"""Centralized wrapper for Claude Code CLI invocations.

All PAM calls to Claude go through `run_claude()`. Handles:
- CLAUDE_BIN resolution via shutil.which / config override
- CREATE_NO_WINDOW flag only on Windows
- UTF-8 encoding, generous timeouts
- Health status for /health endpoint
"""

import asyncio
import shutil
import subprocess
import sys

from app.config import settings

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def claude_binary() -> str | None:
    """Resolve the Claude CLI path, or None if not installed."""
    candidate = settings.claude_bin
    resolved = shutil.which(candidate)
    return resolved


def is_available() -> bool:
    return claude_binary() is not None


async def run_claude(prompt: str, timeout: int = 60, extra_args: list[str] | None = None) -> dict:
    """Run `claude --print -p <prompt>`. Returns {"ok": bool, "text": str, "error": str}."""
    binary = claude_binary()
    if not binary:
        return {
            "ok": False,
            "text": "",
            "error": "Claude CLI not installed. See https://docs.claude.com/claude-code",
        }
    cmd = [binary, "--print", "-p", prompt]
    if extra_args:
        cmd.extend(extra_args)
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            creationflags=_CREATION_FLAGS,
        )
        if result.returncode != 0:
            return {"ok": False, "text": "", "error": (result.stderr or "").strip()[:500]}
        return {"ok": True, "text": (result.stdout or "").strip(), "error": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "error": f"Claude CLI timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "text": "", "error": str(e)}


async def health() -> dict:
    """Lightweight health check for the /health endpoint."""
    if not is_available():
        return {"status": "not_installed", "binary": settings.claude_bin}
    # Don't actually invoke the CLI here — it's slow and costs tokens.
    # The binary presence is a sufficient live check.
    return {"status": "ok", "binary": claude_binary()}
