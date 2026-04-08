# Create and distribute a plugin marketplace -- Claude Code Documentation

> Source: https://code.claude.com/docs/en/plugin-marketplaces
> Saved: 2026-04-08

A plugin marketplace is a catalog that lets you distribute plugins to others. Marketplaces provide centralized discovery, version tracking, automatic updates, and support for multiple source types (git repositories, local paths, and more).

## Overview

1. Create plugins (commands, agents, hooks, MCP servers, LSP servers)
2. Create a `marketplace.json` listing your plugins
3. Host the marketplace (GitHub, GitLab, or another git host)
4. Share with users via `/plugin marketplace add`

## Create the marketplace file

Create `.claude-plugin/marketplace.json` in repository root with `name`, `owner`, and `plugins` array.

## Marketplace schema

**Required fields:**
- `name` (kebab-case)
- `owner` (object with `name` required, `email` optional)
- `plugins` (array)

Reserved marketplace names include: `claude-code-marketplace`, `claude-code-plugins`, `anthropic-marketplace`, etc.

**Optional metadata:** `metadata.description`, `metadata.version`, `metadata.pluginRoot`.

## Plugin entries

Each plugin needs `name` and `source`. Optional fields: `description`, `version`, `author`, `homepage`, `repository`, `license`, `keywords`, `category`, `tags`, `strict`, plus component configs (`commands`, `agents`, `hooks`, `mcpServers`, `lspServers`).

## Plugin sources

| Source | Type | Notes |
|--------|------|-------|
| Relative path | string (`./my-plugin`) | Local directory within marketplace repo |
| `github` | object | `repo`, optional `ref`, `sha` |
| `url` | object | Git URL, optional `ref`, `sha` |
| `git-subdir` | object | Subdirectory within a repo (sparse clone) |
| `npm` | object | `package`, optional `version`, `registry` |

## Strict mode

| Value | Behavior |
|:------|:---------|
| `true` (default) | `plugin.json` is the authority; marketplace can supplement |
| `false` | Marketplace entry is the entire definition |

## Host and distribute

**GitHub (recommended):** Create repo, add `.claude-plugin/marketplace.json`, share with `/plugin marketplace add owner/repo`.

**Other git services:** Any git host works via full URL.

**Private repositories:** Uses existing git credential helpers. For auto-updates, set tokens: `GITHUB_TOKEN`/`GH_TOKEN`, `GITLAB_TOKEN`/`GL_TOKEN`.

## Require marketplaces for team

Add to `.claude/settings.json` via `extraKnownMarketplaces` and `enabledPlugins`.

## Pre-populate plugins for containers

Use `CLAUDE_CODE_PLUGIN_SEED_DIR` to point at a pre-built plugins directory.

## Managed marketplace restrictions

`strictKnownMarketplaces` in managed settings controls which marketplaces users can add.

## CLI commands

```bash
claude plugin marketplace add <source> [--scope user|project|local] [--sparse <paths...>]
claude plugin marketplace list [--json]
claude plugin marketplace remove <name>
claude plugin marketplace update [name]
```

## Validation and testing

```bash
claude plugin validate .
/plugin marketplace add ./path/to/marketplace
/plugin install test-plugin@marketplace-name
```

## Key takeaway for ForgeFrame

ForgeFrame can be distributed as a **plugin marketplace** on GitHub. The repo needs:
1. `.claude-plugin/marketplace.json` -- marketplace manifest
2. `plugin.json` -- plugin manifest defining skills and MCP server
3. `skills/` -- Claude Code skill files
4. MCP server code -- the Python MCP server

Users install with: `/plugin marketplace add Caleb68864/ForgeFrame`
Then: `/plugin install forgeframe@forgeframe-marketplace`

This gives them both the skills AND the MCP server in one install.
