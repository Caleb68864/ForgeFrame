"""Discover registered capabilities from source without importing AI engines."""
from __future__ import annotations

import ast
from pathlib import Path

import yaml


def capability_catalog() -> dict:
    package = Path(__file__).resolve().parents[1]
    tools = []
    sources = [package / 'server.py']
    for relative in ('edit_mcp/server/tools', 'edit_mcp/server/bundles',
                     'edit_mcp/pipelines/effect_wrappers'):
        sources.extend(sorted((package / relative).glob('*.py')))
    for source in sources:
        tree = ast.parse(source.read_text(encoding='utf-8'))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            registered_name = node.name
            registered = False
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(target, ast.Name) and target.id == 'register_effect_wrapper':
                    registered = True
                if (isinstance(target, ast.Attribute) and target.attr == 'tool'
                        and isinstance(target.value, ast.Name) and target.value.id == 'mcp'):
                    registered = True
                    if isinstance(decorator, ast.Call):
                        for keyword in decorator.keywords:
                            if keyword.arg == 'name' and isinstance(keyword.value, ast.Constant):
                                registered_name = keyword.value.value
            if registered:
                tools.append({'name': registered_name,
                              'category': source.stem,
                              'description': (ast.get_docstring(node) or '').split('\n')[0]})
    skills_root = next((ancestor / 'skills' for ancestor in package.parents
                        if (ancestor / 'skills').is_dir()), None)
    skills = []
    if skills_root:
        for skill in sorted(skills_root.glob('ff-*/SKILL.md')):
            content = skill.read_text(encoding='utf-8')
            metadata = yaml.safe_load(content.split('---', 2)[1]) if content.startswith('---') else {}
            skills.append({'name': metadata.get('name', skill.parent.name),
                           'description': ' '.join(str(metadata.get('description', '')).split())})
    return {'tools': sorted(tools, key=lambda item: item['name']), 'skills': skills,
            'tool_count': len(tools), 'skill_count': len(skills),
            'skills_available': skills_root is not None,
            'source': 'MCP decorators and effect-wrapper registration; skill frontmatter'}


def catalog_markdown() -> str:
    catalog = capability_catalog()
    lines = ['# ForgeFrame capabilities', '',
             'Generated with `wvb capabilities --markdown`. Registration metadata is the source of truth.', '',
             f"{catalog['tool_count']} MCP tools; {catalog['skill_count']} skills.", '',
             '## Skills', '', '| Skill | Description |', '| --- | --- |']
    for item in catalog['skills']:
        lines.append(f"| {item['name']} | {item['description'].replace('|', '/') } |")
    lines.extend(['', '## MCP tools', '', '| Tool | Module | Description |', '| --- | --- | --- |'])
    for item in catalog['tools']:
        description = item['description'].replace('|', '/').replace('\n', ' ')
        lines.append(f"| {item['name']} | {item['category']} | {description} |")
    return '\n'.join(lines) + '\n'
