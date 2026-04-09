"""Tests for extended FFprobe capabilities: VFR detection, color metadata, loudness."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media, measure_loudness


# Mock ffprobe output for a VFR file (r_frame_rate and avg_frame_rate diverge >5%)
VFR_PROBE_OUTPUT = {
    "format": {
        "filename": "test_vfr.mp4",
        "duration": "10.0",
        "size": "1000000",
        "bit_rate": "800000",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "avg_frame_rate": "25/1",
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
        }
    ],
}

# Mock ffprobe output for a CFR file (rates match)
CFR_PROBE_OUTPUT = {
    "format": {
        "filename": "test_cfr.mp4",
        "duration": "10.0",
        "size": "1000000",
        "bit_rate": "800000",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
        }
    ],
}

# Mock ffprobe output with missing color metadata
NO_COLOR_PROBE_OUTPUT = {
    "format": {
        "filename": "test_no_color.mp4",
        "duration": "10.0",
        "size": "1000000",
        "bit_rate": "800000",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
        }
    ],
}


def _mock_probe(output_dict):
    """Create a mock for subprocess.run that returns ffprobe JSON."""
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(output_dict)
    mock_result.returncode = 0
    return mock_result


class TestVFRDetection:
    @patch("subprocess.run")
    def test_vfr_file_detected(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(VFR_PROBE_OUTPUT)
        test_file = tmp_path / "test_vfr.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.is_vfr is True

    @patch("subprocess.run")
    def test_cfr_file_not_flagged(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(CFR_PROBE_OUTPUT)
        test_file = tmp_path / "test_cfr.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.is_vfr is False


class TestColorMetadata:
    @patch("subprocess.run")
    def test_color_metadata_extracted(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(CFR_PROBE_OUTPUT)
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.color_space == "bt709"
        assert asset.color_primaries == "bt709"
        assert asset.color_transfer == "bt709"

    @patch("subprocess.run")
    def test_missing_color_defaults_none(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(NO_COLOR_PROBE_OUTPUT)
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.color_space is None
        assert asset.color_primaries is None
        assert asset.color_transfer is None


class TestLoudnessMeasurement:
    @patch("subprocess.run")
    def test_measure_loudness_parses_output(self, mock_run, tmp_path):
        loudnorm_output = (
            '[Parsed_loudnorm_0 @ 0x0] \n'
            '{\n'
            '    "input_i" : "-23.5",\n'
            '    "input_tp" : "-1.2",\n'
            '    "input_lra" : "8.3"\n'
            '}\n'
        )
        mock_result = MagicMock()
        mock_result.stderr = loudnorm_output
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"\x00" * 100)

        result = measure_loudness(test_file)

        assert result is not None
        assert result.input_i == pytest.approx(-23.5)
        assert result.input_tp == pytest.approx(-1.2)
        assert result.input_lra == pytest.approx(8.3)

    @patch("subprocess.run")
    def test_measure_loudness_handles_failure(self, mock_run, tmp_path):
        mock_run.side_effect = Exception("ffmpeg not found")
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"\x00" * 100)

        result = measure_loudness(test_file)

        assert result is None
