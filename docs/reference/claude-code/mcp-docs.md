# Connect Claude Code to tools via MCP -- Claude Code Documentation

> Source: https://code.claude.com/docs/en/mcp
> Saved: 2026-04-08

Claude Code can connect to hundreds of external tools and data sources through the Model Context Protocol (MCP), an open source standard for AI-tool integrations.

## Installing MCP servers

**Option 1: Remote HTTP server** (recommended for cloud-based services):
```bash
claude mcp add --transport http <name> <url>
```

**Option 2: Local stdio server:**
```bash
claude mcp add [options] <name> -- <command> [args...]
claude mcp add --transport stdio --env AIRTABLE_API_KEY=YOUR_KEY airtable -- npx -y airtable-mcp-server
```

All options (`--transport`, `--env`, `--scope`, `--header`) must come before the server name. The `--` separates the server name from the command.

**Managing servers:**
```bash
claude mcp list
claude mcp get github
claude mcp remove github
/mcp  # within Claude Code
```

## MCP installation scopes

| Scope | Loads in | Shared with team | Stored in |
|-------|----------|------------------|-----------|
| Local | Current project only | No | `~/.claude.json` |
| Project | Current project only | Yes, via version control | `.mcp.json` in project root |
| User | All your projects | No | `~/.claude.json` |

Precedence: local > project > user.

## Environment variable expansion in `.mcp.json`

`${VAR}` and `${VAR:-default}` supported in command, args, env, url, and headers fields.

## Plugin-provided MCP servers

Plugins can bundle MCP servers via `.mcp.json` or inline in `plugin.json`. They start automatically when the plugin is enabled. Use `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` for paths.

## Authentication

OAuth 2.0 supported. Add the server, then run `/mcp` and follow browser login.

- **Fixed callback port:** `--callback-port`
- **Pre-configured OAuth:** `--client-id`, `--client-secret`, `--callback-port`
- **Dynamic headers (headersHelper):** Run a shell command to generate auth headers at connection time

## Use Claude Code as an MCP server

```bash
claude mcp serve
```
Exposes Claude Code's tools (View, Edit, LS, etc.) to other applications.

## MCP output limits

- Warning threshold: 10,000 tokens
- Default maximum: 25,000 tokens
- Configurable via `MAX_MCP_OUTPUT_TOKENS`
- Server authors can set `_meta["anthropic/maxResultSizeChars"]` per tool (up to 500,000 chars)

## MCP resources

Reference resources with `@server:protocol://resource/path`. Resources appear in @ mention autocomplete.

## Tool Search

Tool search is enabled by default. MCP tools are deferred and discovered on demand, keeping context usage low.

## MCP prompts as commands

MCP prompts appear as `/mcp__servername__promptname` commands.

## Managed MCP configuration

**Option 1: Exclusive control with `managed-mcp.json`:**
- macOS: `/Library/Application Support/ClaudeCode/managed-mcp.json`
- Linux/WSL: `/etc/claude-code/managed-mcp.json`

**Option 2: Policy-based control** with `allowedMcpServers` and `deniedMcpServers` in managed settings.
