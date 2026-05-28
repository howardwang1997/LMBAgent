"""Sandbox enforcement for the development workspace.

All file/command operations from the coding agent are validated through
this module. Inspired by opencode's permission system, simplified for
our single-directory sandbox model.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Optional

SANDBOX_ROOT = (Path(__file__).parent.parent.parent.parent / "workspace").resolve()

UPLOAD_DIR = SANDBOX_ROOT / "uploads"

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

MAX_OUTPUT_SIZE = 50 * 1024  # 50 KB tool output truncation

BLOCKED_COMMAND_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/(\s|$)",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r":\(\)\{\s*:\|:&",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\b(init\s+[06])\b",
    r"\bpip\s+uninstall\b",
    r"\bconda\s+remove\b",
    r"\bgit\s+push\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+checkout\s+--\s+\.\b",
    r"\bgit\s+clean\b",
    r"\bgit\s+rebase\b",
    r"\bchmod\s+(-R\s+)?[0-7]*777\b",
    r"\bchown\b",
    r"\bkill\s+-9\s+1\b",
    r"\bkillall\b",
    r"\bps\b",
    r"\btop\b",
    r"\bhtop\b",
    r"\bnohup\b",
    r"\bsetsid\b",
    r"\bsudo\b",
    r"\bnc\b.*-l",
    r"\bpython\s+-m\s+http\.server\b",
    r"\bscreen\b",
    r"\btmux\b",
]


def ensure_dirs() -> None:
    """Create sandbox directories if they don't exist."""
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def validate_path(path: str, must_exist: bool = False, allow_create: bool = True) -> Path:
    """Validate and resolve a path within the sandbox.

    Args:
        path: Relative path (to sandbox root) or absolute path.
        must_exist: If True, the path must already exist.
        allow_create: If True, parent directories can be created.

    Returns:
        Resolved absolute path within sandbox.

    Raises:
        ValueError: If path escapes sandbox or violates constraints.
    """
    p = Path(path)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (SANDBOX_ROOT / p).resolve()

    if not resolved.is_relative_to(SANDBOX_ROOT):
        raise ValueError(f"路径超出沙箱范围: {path} (resolved: {resolved}, sandbox: {SANDBOX_ROOT})")

    if str(resolved) == str(SANDBOX_ROOT) and not allow_create:
        raise ValueError("不能操作沙箱根目录本身")

    if must_exist and not resolved.exists():
        raise ValueError(f"路径不存在: {path}")

    return resolved


def validate_command(cmd: str) -> str:
    """Validate a shell command for safety.

    Args:
        cmd: Shell command string.

    Returns:
        The command if valid.

    Raises:
        ValueError: If command contains blocked patterns.
    """
    for pattern in BLOCKED_COMMAND_PATTERNS:
        if re.search(pattern, cmd):
            raise ValueError(f"禁止的命令模式: {pattern}")

    return cmd


def validate_file_size(size: int) -> None:
    """Check file size against upload limit."""
    if size > MAX_FILE_SIZE:
        raise ValueError(f"文件大小 {size:,} bytes 超过限制 {MAX_FILE_SIZE:,} bytes ({MAX_FILE_SIZE // 1024 // 1024} MB)")


def truncate_output(output: str, max_bytes: int = MAX_OUTPUT_SIZE) -> str:
    """Truncate tool output to fit in LLM context."""
    encoded = output.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return output

    truncated = encoded[: max_bytes - 100].decode("utf-8", errors="replace")
    return truncated + f"\n\n... [输出截断: {len(encoded):,} bytes, 显示前 {max_bytes:,} bytes]"


def list_workspace_files(pattern: str = "**/*") -> list[dict]:
    """List files in workspace matching a glob pattern."""
    ensure_dirs()
    files = []
    for p in sorted(SANDBOX_ROOT.glob(pattern)):
        if p.is_file():
            rel = p.relative_to(SANDBOX_ROOT)
            stat = p.stat()
            files.append({
                "path": str(rel),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    return files


def workspace_tree(max_depth: int = 3) -> str:
    """Generate a text tree of the workspace directory."""
    ensure_dirs()
    lines = ["workspace/"]

    def _walk(directory: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir() and not entry.name.startswith("."):
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    _walk(SANDBOX_ROOT, "", 0)
    return "\n".join(lines[:200])
