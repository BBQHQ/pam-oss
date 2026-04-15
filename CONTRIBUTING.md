# Contributing to PAM

Thanks for poking around. PAM is a small project with strong design opinions. Read
these before you start cutting a PR.

## Design principles

1. **Single-user, self-hosted, no auth.** PAM runs on your box for you. If you want multi-tenant SaaS, fork it and build that separately.
2. **Claude-first.** AI calls use the Claude Code CLI via `app/services/claude_cli.py::run_claude()`. Don't reintroduce shell-outs to `claude` elsewhere.
3. **Optional integrations self-disable.** If your feature needs an external credential, check at startup and log "X disabled: credential not found" as info (not error). Hide the UI surface cleanly. Don't crash.
4. **SQLite only.** No Postgres, no ORMs, no migration frameworks. Use idempotent `CREATE TABLE IF NOT EXISTS` inside a `_get_db()` helper per service.
5. **Cross-platform.** Guard Windows-only flags (`subprocess.CREATE_NO_WINDOW`) via `_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0`.
6. **No RAG, no vector DB.** Claude gets fresh context every call. If you want persistent memory, it lives in the SQLite `memory` table (exposed as `/settings`).

## Project layout

See `CLAUDE.md`.

## Getting the repo running

```bash
git clone <this-repo>
cd pam
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
cp .env.example .env
./scripts/install_whisper.sh   # or .ps1 on Windows
python -m app.main
```

Open `https://localhost:8400`. Accept the self-signed cert.

## Code style

- **Python**: `ruff` for lint; no black. Double quotes. f-strings. `snake_case`.
- **Async-first**: services return coroutines. Use `aiosqlite`, `httpx.AsyncClient`, `asyncio.to_thread` for blocking calls.
- **Frontend**: vanilla JS, no framework, no build step. Plain CSS. Keep it simple.
- **Subprocess calls**: always `encoding="utf-8"`, reasonable timeouts, `_CREATION_FLAGS` for Windows compat.
- **No comments for *what***. Only for *why* when non-obvious.

## Submitting a PR

1. Fork, branch from `main`.
2. Keep PRs small — one feature or one fix.
3. Test your change locally. If you added a router, make sure `GET /health` still passes.
4. Update `CLAUDE.md` if you added a new service pattern. Update `README.md` if you changed a user-visible surface.
5. Open the PR with a short description and a "how to test" block.

## Scope

**In scope**: new features that fit a single-user personal-assistant model. Cross-platform portability fixes. Better UX on the existing pages. Docs.

**Out of scope for v1**: multi-user / auth. Non-Claude AI backends (maybe v2). Mobile native apps. Remote-exposed installs. Docker — PAM is a plain Python app, and the proprietary Claude CLI + platform-specific whisper build don't play nicely with container abstractions.

If you're unsure, open an issue first and ask.
