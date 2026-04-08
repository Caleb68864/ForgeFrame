# The Complete Guide to Building Skills for Claude

> Source: https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf
> Saved: 2026-04-08

## Contents

- Introduction
- Fundamentals
- Planning and design
- Testing and iteration
- Distribution and sharing
- Patterns and troubleshooting
- Resources and references

---

## Introduction

A **skill** is a set of instructions - packaged as a simple folder - that teaches Claude how to handle specific tasks or workflows. Skills are one of the most powerful ways to customize Claude for your specific needs. Instead of re-explaining your preferences, processes, and domain expertise in every conversation, skills let you teach Claude once and benefit every time.

Skills are powerful when you have repeatable workflows: generating frontend designs from specs, conducting research with consistent methodology, creating documents that follow your team's style guide, or orchestrating multi-step processes. They work well with Claude's built-in capabilities like code execution and document creation. For those building MCP integrations, skills add another powerful layer helping turn raw tool access into reliable, optimized workflows.

## Chapter 1: Fundamentals

### What is a skill?

A skill is a folder containing:
- **SKILL.md** (required): Instructions in Markdown with YAML frontmatter
- **scripts/** (optional): Executable code (Python, Bash, etc.)
- **references/** (optional): Documentation loaded as needed
- **assets/** (optional): Templates, fonts, icons used in output

### Core design principles

**Progressive Disclosure**

Skills use a three-level system:

- **First level (YAML frontmatter):** Always loaded in Claude's system prompt. Provides just enough information for Claude to know when each skill should be used without loading all of it into context.
- **Second level (SKILL.md body):** Loaded when Claude thinks the skill is relevant to the current task. Contains the full instructions and guidance.
- **Third level (Linked files):** Additional files bundled within the skill directory that Claude can choose to navigate and discover only as needed.

**Composability**

Claude can load multiple skills simultaneously. Your skill should work well alongside others, not assume it's the only capability available.

**Portability**

Skills work identically across Claude.ai, Claude Code, and API. Create a skill once and it works across all surfaces without modification, provided the environment supports any dependencies the skill requires.

### For MCP Builders: Skills + Connectors

**The kitchen analogy**

**MCP provides the professional kitchen:** access to tools, ingredients, and equipment.
**Skills provide the recipes:** step-by-step instructions on how to create something valuable.

| MCP (Connectivity) | Skills (Knowledge) |
|---|---|
| Connects Claude to your service | Teaches Claude how to use your service effectively |
| Provides real-time data access and tool invocation | Captures workflows and best practices |
| What Claude can do | How Claude should do it |

## Chapter 2: Planning and design

### Start with use cases

Before writing any code, identify 2-3 concrete use cases your skill should enable.

### Common skill use case categories

**Category 1: Document & Asset Creation** - Creating consistent, high-quality output including documents, presentations, apps, designs, code, etc.

**Category 2: Workflow Automation** - Multi-step processes that benefit from consistent methodology, including coordination across multiple MCP servers.

**Category 3: MCP Enhancement** - Workflow guidance to enhance the tool access an MCP server provides.

### Technical requirements

**File structure**

```
your-skill-name/
├── SKILL.md                # Required - main skill file
├── scripts/                # Optional - executable code
├── references/             # Optional - documentation
└── assets/                 # Optional - templates, etc.
```

**Critical rules**

- SKILL.md naming must be exactly `SKILL.md` (case-sensitive)
- Skill folder naming: use kebab-case, no spaces, no underscores, no capitals
- No README.md inside your skill folder

### YAML frontmatter

**Minimal required format:**

```yaml
---
name: your-skill-name
description: What it does. Use when user asks to [specific phrases].
---
```

**Field requirements:**

- **name** (required): kebab-case only, no spaces or capitals, should match folder name
- **description** (required): MUST include BOTH what the skill does AND when to use it (trigger conditions). Under 1024 characters. No XML tags.
- **license** (optional): Use if making skill open source
- **compatibility** (optional): 1-500 characters, indicates environment requirements
- **metadata** (optional): Any custom key-value pairs (author, version, mcp-server)

**Security restrictions:** No XML angle brackets (< >) in frontmatter. No "claude" or "anthropic" in name.

### Writing effective descriptions

**Structure:** `[What it does] + [When to use it] + [Key capabilities]`

Good examples:
```
description: Analyzes Figma design files and generates developer handoff documentation. Use when user uploads .fig files, asks for "design specs", "component documentation", or "design-to-code handoff".
```

Bad examples:
```
description: Helps with projects.
```

### Recommended SKILL.md structure

```markdown
---
name: your-skill
description: [...]
---

# Your Skill Name

## Instructions
### Step 1: [First Major Step]
(clear explanation + example commands)

## Examples
### Example 1: [common scenario]

## Troubleshooting
### Error: [Common error message]
```

## Chapter 3: Testing and iteration

### Recommended Testing Approach

**1. Triggering tests** - Ensure your skill loads at the right times (should trigger, should NOT trigger lists).

**2. Functional tests** - Verify the skill produces correct outputs.

**3. Performance comparison** - Prove the skill improves results vs. baseline.

### Using the skill-creator skill

The `skill-creator` skill can help you build and iterate on skills. Available in Claude.ai via plugin directory or download for Claude Code.

### Iteration based on feedback

- **Undertriggering:** Add more detail and nuance to the description
- **Overtriggering:** Add negative triggers, be more specific
- **Execution issues:** Improve instructions, add error handling

## Chapter 4: Distribution and sharing

### Current distribution model (January 2026)

**How individual users get skills:**
1. Download the skill folder
2. Zip the folder (if needed)
3. Upload to Claude.ai via Settings > Capabilities > Skills
4. Or place in Claude Code skills directory

**Organization-level skills:** Admins can deploy skills workspace-wide.

### An open standard

Agent Skills is published as an open standard (agentskills.io). Like MCP, skills should be portable across tools and platforms.

### Using skills via API

- `/v1/skills` endpoint for listing and managing skills
- Add skills to Messages API requests via the `container.skills` parameter
- Works with the Claude Agent SDK for building custom agents

### Recommended approach today

1. Host on GitHub with a public repo, clear README, and example usage
2. Document in Your MCP Repo -- link to skills from MCP documentation
3. Create an Installation Guide

## Chapter 5: Patterns and troubleshooting

### Pattern 1: Sequential workflow orchestration
Multi-step processes in a specific order with explicit step ordering, dependencies, validation, and rollback.

### Pattern 2: Multi-MCP coordination
Workflows spanning multiple services with clear phase separation and data passing between MCPs.

### Pattern 3: Iterative refinement
Output quality improves with iteration -- initial draft, quality check, refinement loop, finalization.

### Pattern 4: Context-aware tool selection
Same outcome, different tools depending on context with clear decision criteria.

### Pattern 5: Domain-specific intelligence
Specialized knowledge beyond tool access with domain expertise embedded in logic.

### Troubleshooting

- **Skill won't upload:** Check SKILL.md naming (case-sensitive), YAML formatting, skill name format
- **Skill doesn't trigger:** Revise description field, add trigger phrases
- **Skill triggers too often:** Add negative triggers, be more specific
- **MCP connection issues:** Verify server connected, check auth, test MCP independently
- **Instructions not followed:** Make instructions concise, put critical ones at top, use explicit language
- **Large context issues:** Move detailed docs to references/, keep SKILL.md under 5,000 words

## Reference A: Quick checklist

**Before you start:**
- [ ] Identified 2-3 concrete use cases
- [ ] Tools identified (built-in or MCP)

**During development:**
- [ ] Folder named in kebab-case
- [ ] SKILL.md file exists (exact spelling)
- [ ] YAML frontmatter has --- delimiters
- [ ] name field: kebab-case, no spaces, no capitals
- [ ] description includes WHAT and WHEN
- [ ] No XML tags (< >) anywhere
- [ ] Instructions are clear and actionable

**Before upload:**
- [ ] Tested triggering on obvious tasks
- [ ] Tested triggering on paraphrased requests
- [ ] Verified doesn't trigger on unrelated topics
- [ ] Functional tests pass
