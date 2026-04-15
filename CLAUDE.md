# CLAUDE.md — PAM development context

This file is read by the Claude Code CLI when it's run against the PAM repo. It's a
lightweight map of the codebase, not a substitute for the README.

## TL;DR

PAM is a single-user self-hosted personal executive assistant. FastAPI backend,
vanilla-JS SPA frontend, SQLite storage, Claude Code CLI as the AI brain, whisper.cpp
for voice.

## Layout

```
app/
├── main.py              # FastAPI app + lifespan (ensures certs, seeds data, starts schedulers)
├── config.py            # Pydantic BaseSettings reading .env
├── models.py            # Pydantic schemas (Project, etc.)
├── routers/             # HTTP endpoints (voice, todos, tasks, notes, settings, etc.)
└── services/            # Business logic (per feature) + shared:
    ├── bootstrap.py     # SSL cert gen + first-boot seed
    ├── claude_cli.py    # Wrapper around `claude --print -p`
    └── whisper.py       # whisper.cpp server lifecycle (auto-start, TTL shutdown)
frontend/
├── index.html           # SPA entry
├── pam.js
├── pam.css
└── sounds/              # Optional SFX (user drop-in, see README)
data/                    # SQLite + JSON state (gitignored)
whisper/                 # Built binary + model (gitignored, produced by scripts/install_whisper)
certs/                   # SSL (gitignored, auto-generated)
scripts/                 # install_whisper, generate_cert
docs/                    # systemd / launchd examples
```

## Design constraints

- **Single-user**: no auth, no per-user data. Trusted-network assumption.
- **Optional integrations self-disable**: Gmail, Google Calendar, GitHub CLI. PAM boots cleanly without any of them.
- **Claude + Whisper are mandatory**: voice transcription and AI features are the whole point.
- **Claude-first**: no RAG, no vector DB. Every AI call is a fresh `claude --print -p` subprocess.
- **SQLite only**: no Postgres, no migrations framework (services use idempotent `CREATE TABLE IF NOT EXISTS`).
- **Cross-platform**: Linux, macOS, Windows. Guard all `CREATE_NO_WINDOW` subprocess flags via `_CREATION_FLAGS`.

## How features talk to Claude

Every Claude call goes through `app/services/claude_cli.py::run_claude()`. Don't shell out directly elsewhere. It handles:
- Binary resolution (via `CLAUDE_BIN` env or `shutil.which`)
- Platform-specific subprocess flags
- UTF-8 encoding, timeouts
- Structured `{"ok", "text", "error"}` return

## Scheduled jobs

Three asyncio loops in `main.py` lifespan:
- Briefing email (default 7:00)
- Mid-day check-in email (default 13:00)
- Habit reset (default 04:00)

All re-read their hour from `/settings` each loop iteration; no restart needed when the user changes schedules.

## When adding new routers

1. Create `app/routers/<name>.py` with `router = APIRouter(prefix="/<name>", tags=["<name>"])`
2. Create `app/services/<name>.py` for logic
3. Add the import + `app.include_router(<name>.router)` in `main.py`
4. If it touches SQLite, use `CREATE TABLE IF NOT EXISTS` in a `_get_db()` helper — no migration framework

## When in doubt

Read `app/main.py` top-to-bottom. It's a small file that tells you how the whole thing fits together.
