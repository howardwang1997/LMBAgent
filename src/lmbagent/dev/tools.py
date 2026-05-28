"""Tool definitions for the development coding agent.

Implements 7 tools inspired by opencode's tool framework:
- read_file, write_file, edit_file, list_files, search_content, run_command, ask_user

Each tool has a JSON schema for the LLM and a handler function that
executes within the sandbox.
"""

from __future__ import annotations

import subprocess
import json
from pathlib import Path
from typing import Any, Callable, Optional

from lmbagent.dev.sandbox import (
    SANDBOX_ROOT,
    validate_path,
    validate_command,
    truncate_output,
    ensure_dirs,
)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read file content from the workspace. Use offset/limit for large files. "
                "Supports text files. Returns file content with line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root (e.g., 'scripts/main.py')",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed). Default: 1",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read. Default: 500",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file in the workspace. Creates parent directories if needed. "
                "Overwrites existing files. Use this to create new scripts or files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Edit a file by replacing exact string matches. Use this for targeted edits "
                "instead of rewriting entire files. The old_string must match exactly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to workspace root",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact string to find and replace",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement string",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files in the workspace matching a glob pattern. "
                "Returns file paths, sizes, and modification times."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g., '**/*.py', 'scripts/*.csv'). Default: '**/*'",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_content",
            "description": (
                "Search file contents using a regex pattern. Like grep. "
                "Returns matching file paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression pattern to search for",
                    },
                    "include": {
                        "type": "string",
                        "description": "File pattern to include (e.g., '*.py', '*.csv'). Default: all files",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Execute a bash command in the workspace directory. "
                "The command runs with cwd set to workspace/. "
                "Timeout: 60 seconds. Use for running scripts, installing packages, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Bash command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default: 60, Max: 300",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Ask the user a clarifying question when you cannot proceed automatically. "
                "Use when the task is ambiguous, requires domain knowledge you lack, "
                "or when you've attempted but failed to solve a problem. "
                "The question will be displayed to the user and their response will be "
                "sent back to you."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Clear, specific question to ask the user",
                    },
                    "context": {
                        "type": "string",
                        "description": "Brief explanation of why you're asking (what you tried, what failed)",
                    },
                },
                "required": ["question"],
            },
        },
    },
]


def handle_read_file(args: dict) -> str:
    path = validate_path(args["path"], must_exist=True)
    offset = args.get("offset", 1)
    limit = args.get("limit", 500)

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file: {e}"

    lines = content.splitlines()
    selected = lines[max(0, offset - 1) : offset - 1 + limit]
    numbered = [f"{i + offset}: {line}" for i, line in enumerate(selected)]

    result = "\n".join(numbered)
    if len(lines) > offset - 1 + limit:
        result += f"\n\n... ({len(lines)} lines total, showing lines {offset}-{offset - 1 + limit})"

    return truncate_output(result)


def handle_write_file(args: dict) -> str:
    path = validate_path(args["path"])
    content = args["content"]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    n_lines = content.count("\n") + 1
    return f"Written {n_lines} lines to {args['path']} ({len(content.encode('utf-8')):,} bytes)"


def handle_edit_file(args: dict) -> str:
    path = validate_path(args["path"], must_exist=True)
    old = args["old_string"]
    new = args["new_string"]

    content = path.read_text(encoding="utf-8")
    count = content.count(old)

    if count == 0:
        return f"Error: old_string not found in {args['path']}. Check whitespace and indentation."
    if count > 1:
        return f"Error: old_string found {count} times in {args['path']}. Provide more context to make it unique."

    updated = content.replace(old, new, 1)
    path.write_text(updated, encoding="utf-8")
    return f"Edited {args['path']}: replaced 1 occurrence"


def handle_list_files(args: dict) -> str:
    from lmbagent.dev.sandbox import list_workspace_files

    pattern = args.get("pattern", "**/*")
    files = list_workspace_files(pattern)

    if not files:
        return f"No files matching '{pattern}'"

    lines = []
    for f in files[:100]:
        size_kb = f["size"] / 1024
        lines.append(f"  {f['path']}  ({size_kb:.1f} KB)")

    result = "\n".join(lines)
    if len(files) > 100:
        result += f"\n\n... ({len(files)} files total, showing first 100)"

    return result


def handle_search_content(args: dict) -> str:
    import re as regex_module

    pattern = args["pattern"]
    include = args.get("include", None)

    ensure_dirs()
    matches = []
    glob_pattern = include if include else "**/*"

    for fpath in sorted(SANDBOX_ROOT.glob(glob_pattern)):
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel = str(fpath.relative_to(SANDBOX_ROOT))
        for i, line in enumerate(text.splitlines(), 1):
            if regex_module.search(pattern, line):
                matches.append(f"{rel}:{i}: {line.strip()}")

    if not matches:
        return f"No matches for pattern '{pattern}'"

    result = "\n".join(matches[:50])
    if len(matches) > 50:
        result += f"\n\n... ({len(matches)} matches total, showing first 50)"

    return truncate_output(result)


def handle_run_command(args: dict) -> str:
    cmd = validate_command(args["command"])
    timeout = min(args.get("timeout", 60), 300)

    ensure_dirs()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(SANDBOX_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **{k: v for k, v in __import__("os").environ.items()
                   if k not in ("HOME", "USER", "PATH") or True},
                "PYTHONPATH": str(SANDBOX_ROOT.parent / "src") + ":" + __import__("os").environ.get("PYTHONPATH", ""),
            },
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s: {cmd}"

    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        output += ("\n--- STDERR ---\n" + result.stderr) if output else result.stderr

    if result.returncode != 0:
        output += f"\n[exit code: {result.returncode}]"

    return truncate_output(output.strip() or "(no output)")


def handle_ask_user(args: dict) -> str:
    return json.dumps({
        "action": "ask_user",
        "question": args["question"],
        "context": args.get("context", ""),
    })


TOOL_HANDLER_MAP: dict[str, Callable[[dict], str]] = {
    "read_file": handle_read_file,
    "write_file": handle_write_file,
    "edit_file": handle_edit_file,
    "list_files": handle_list_files,
    "search_content": handle_search_content,
    "run_command": handle_run_command,
    "ask_user": handle_ask_user,
}
