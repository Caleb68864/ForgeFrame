# Extend Claude with skills -- Claude Code Documentation

> Source: https://code.claude.com/docs/en/skills
> Saved: 2026-04-08

Skills extend what Claude can do. Create a `SKILL.md` file with instructions, and Claude adds it to its toolkit. Claude uses skills when relevant, or you can invoke one directly with `/skill-name`.

**Note:** Custom commands have been merged into skills. A file at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md` both create `/deploy` and work the same way. Your existing `.claude/commands/` files keep working.

Claude Code skills follow the Agent Skills open standard (agentskills.io).

## Bundled skills

| Skill | Purpose |
|:------|:--------|
| `/batch <instruction>` | Orchestrate large-scale changes across a codebase in parallel |
| `/claude-api` | Load Claude API reference material for your project's language |
| `/debug [description]` | Enable debug logging and troubleshoot issues |
| `/loop [interval] <prompt>` | Run a prompt repeatedly on an interval |
| `/simplify [focus]` | Review recently changed files for code quality, then fix them |

## Where skills live

| Location | Path | Applies to |
|:---------|:-----|:-----------|
| Enterprise | See managed settings | All users in organization |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` | All your projects |
| Project | `.claude/skills/<skill-name>/SKILL.md` | This project only |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` | Where plugin is enabled |

When skills share the same name across levels, higher-priority locations win: enterprise > personal > project. Plugin skills use `plugin-name:skill-name` namespace.

## Configure skills -- Frontmatter reference

| Field | Description |
|:------|:------------|
| `name` | Display name. Lowercase letters, numbers, hyphens (max 64 chars). |
| `description` | What it does and when to use it. Descriptions > 250 chars are truncated. |
| `argument-hint` | Hint shown during autocomplete, e.g. `[issue-number]`. |
| `disable-model-invocation` | Set `true` to prevent Claude from auto-loading. |
| `user-invocable` | Set `false` to hide from the `/` menu. |
| `allowed-tools` | Tools Claude can use without asking permission. |
| `model` | Model to use when skill is active. |
| `effort` | Effort level: `low`, `medium`, `high`, `max` (Opus 4.6 only). |
| `context` | Set to `fork` to run in a forked subagent context. |
| `agent` | Which subagent type to use when `context: fork`. |
| `hooks` | Hooks scoped to this skill's lifecycle. |
| `paths` | Glob patterns limiting when skill is activated. |
| `shell` | Shell for inline commands: `bash` (default) or `powershell`. |

**String substitutions:** `$ARGUMENTS`, `$ARGUMENTS[N]` / `$N`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_SKILL_DIR}`.

## Advanced patterns

**Inject dynamic context:** The `` !`<command>` `` syntax runs shell commands before the skill content is sent to Claude.

**Run skills in a subagent:** Add `context: fork` to frontmatter. The `agent` field specifies the subagent type.

**Restrict Claude's skill access:** Deny the Skill tool in `/permissions`, allow/deny specific skills using permission rules.

## Share skills

- Project: commit `.claude/skills/` to version control
- Plugins: create a `skills/` directory in your plugin
- Managed: deploy organization-wide through managed settings

## Troubleshooting

- Skill not triggering: check description keywords, verify visibility, invoke directly
- Skill triggers too often: make description more specific or set `disable-model-invocation: true`
- Skill descriptions cut short: descriptions loaded with character budget (1% of context window, fallback 8,000 chars). Set `SLASH_COMMAND_TOOL_CHAR_BUDGET` to increase.
