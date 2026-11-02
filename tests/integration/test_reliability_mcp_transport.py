"""Reliability tools exercised through a real MCP stdio subprocess."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import time
from uuid import uuid4

import pytest

pytest.importorskip("fastmcp")
pytestmark = [
    pytest.mark.external,
    # Skip before each test body builds its ``scenario()`` coroutine, so an
    # absent server never leaves a never-awaited coroutine behind.
    pytest.mark.skipif(
        not shutil.which("workshop-video-brain-server"),
        reason="workshop-video-brain-server is not on PATH",
    ),
]


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=120))


def _client(tmp_path):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    return Client(StdioTransport(
        command="workshop-video-brain-server", args=[],
        env={**os.environ, "HF_HUB_CACHE": str(tmp_path / "empty-model-cache"),
             "U2NET_HOME": str(tmp_path / "empty-mask-cache"),
             "HF_HUB_OFFLINE": "1", "QT_QPA_PLATFORM": "offscreen"},
    ))


async def _call(client, name, arguments):
    result = await client.call_tool(name, arguments)
    payload = result.data
    assert isinstance(payload, dict), (name, payload)
    return payload


def test_reliability_discovery_and_offline_doctor(tmp_path):
    async def scenario():
        async with _client(tmp_path) as client:
            names = {tool.name for tool in await client.list_tools()}
            required = {"job_submit", "job_status", "job_list", "job_cancel", "job_retry",
                        "project_status", "workflow_start", "forgeframe_doctor",
                        "forgeframe_capabilities"}
            assert required <= names
            catalog = await _call(client, "forgeframe_capabilities", {})
            assert required <= {tool["name"] for tool in catalog["tools"]}
            assert catalog["tool_count"] == len(catalog["tools"])
            doctor = await _call(client, "forgeframe_doctor", {})
            assert {"ffmpeg", "ffprobe", "melt"} <= doctor["binaries"].keys()
            assert doctor["model_cache"]["whisper"] == []
            assert doctor["features"]["transcription_offline"] is False
            assert not (tmp_path / "empty-model-cache").exists()
    _run(scenario())


def test_reliability_errors_do_not_break_transport(tmp_path):
    async def scenario():
        async with _client(tmp_path) as client:
            for name, arguments in (
                ("project_status", {"workspace_path": str(tmp_path)}),
                ("job_status", {"workspace_path": str(tmp_path), "job_id": "bad-id"}),
                ("workflow_start", {"workspace_path": str(tmp_path), "through": "publish"}),
            ):
                assert (await _call(client, name, arguments))["status"] == "error"
            (tmp_path / "workspace.yaml").write_text("name: transport-tests\n")
            invalid = await _call(client, "job_submit", {
                "workspace_path": str(tmp_path), "operation": "not-an-operation"})
            assert invalid["status"] == "error"
            status = await _call(client, "project_status", {"workspace_path": str(tmp_path)})
            assert status["status"] == "success"
            assert "readiness" in status["data"]
            assert (await _call(client, "job_list", {"workspace_path": str(tmp_path)}))["data"]["jobs"] == []
    _run(scenario())


@pytest.mark.skipif(os.name != "posix", reason="detached worker requires POSIX")
def test_detached_job_failure_retry_and_recovery_across_connections(tmp_path):
    (tmp_path / "workspace.yaml").write_text("name: transport-tests\n")
    (tmp_path / "jobs").mkdir()
    lost_id = str(uuid4())
    lost = {"id": lost_id, "operation": "proxy", "parameters": {}, "status": "running",
            "created_at": time.time() - 60, "updated_at": time.time() - 60,
            "pid": None, "outputs": [], "progress": {}, "error": ""}
    with sqlite3.connect(tmp_path / "jobs/jobs.sqlite3") as connection:
        connection.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
        connection.execute("INSERT INTO jobs VALUES (?, ?)", (lost_id, json.dumps(lost)))

    async def wait_terminal(client, job_id):
        for _ in range(200):
            response = await _call(client, "job_status", {
                "workspace_path": str(tmp_path), "job_id": job_id})
            assert response["status"] == "success"
            record = response["data"]
            if record["status"] not in {"queued", "running", "cancelling"}:
                return record
            await asyncio.sleep(0.1)
        pytest.fail("Detached job did not reach a terminal state")

    async def scenario():
        arguments = {"workspace_path": str(tmp_path)}
        async with _client(tmp_path) as client:
            recovered = await _call(client, "job_status", {**arguments, "job_id": lost_id})
            assert recovered["data"]["status"] == "interrupted"
            started = await _call(client, "job_submit", {
                **arguments, "operation": "workflow", "parameters": {"through": "footage"}})
            assert started["status"] == "success"
            job_id = started["data"]["id"]
        # Closing the first MCP process must not lose the detached job or its record.
        async with _client(tmp_path) as client:
            failed = await wait_terminal(client, job_id)
            assert failed["status"] == "failed"
            assert failed["error"]
            cancelled = await _call(client, "job_cancel", {**arguments, "job_id": job_id})
            assert cancelled["data"]["status"] == "failed"  # terminal cancel is idempotent
            retried = await _call(client, "job_retry", {**arguments, "job_id": job_id})
            assert retried["status"] == "success"
            retry_id = retried["data"]["id"]
            assert retry_id != job_id
            assert (await wait_terminal(client, retry_id))["status"] == "failed"
            listed = await _call(client, "job_list", arguments)
            assert {lost_id, job_id, retry_id} <= {r["id"] for r in listed["data"]["jobs"]}
    _run(scenario())
