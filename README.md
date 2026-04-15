# PAM — Personal Assistant Manager

A self-hosted personal executive assistant. One person, one install, one home
network. PAM combines a FastAPI backend, a single-page browser dashboard, and
the Claude Code CLI as its AI brain — then layers in voice transcription,
to-dos, habits, notes, kanban projects, calendar parsing, daily briefing
emails, and a gratitude/reflection surface.

Everything lives locally in SQLite. No SaaS tenants, no cloud state, no vendor
lock-in beyond the AI model itself.

> **Status**: v0.1 — functional, single-user, open to feedback.
> **License**: MIT
> **Target user**: a technical solo operator who wants a private workspace.

---

## What it does

- **Voice** — browser-mic recording, local whisper.cpp transcription, auto-routing to to-dos / notes / tasks
- **To-dos** — categories, sub-tasks, dashboard widget, daily-briefing integration
- **Habits** — recurring, streak tracking, 4 AM reset, anti-nag (no overdue state, no guilt)
- **Notes** — pinned notes, AI-enhanced restructuring, question/feedback loop
- **Tasks** — PAM's automation queue with Claude routing to projects
- **Projects** — keyword-matched registry that routes voice/tasks to the right lane
- **Kanban boards** — 4 columns, drag-drop, stale-card detection, daily-briefing integration
- **Calendar** — Google Calendar (optional), natural-language event creation, image-of-an-appointment-card parsing
- **Wins / accomplishments** — auto-captured from completed todos, answered questions, done tasks
- **Gratitude** — curated "pillars" + auto-enriched progress tiles
- **Prompts** — library of your favorite prompts, animated "golden" tiles for starred ones
- **Daily briefing + check-in** — Claude-generated, emailed at 7 AM + 1 PM (optional)
- **Settings** — runtime tweaks for schedule hours, timezone, SFX, email recipient

---

## Install

### Prerequisites

Required:
- **Python 3.11+**
- **git**
- **ffmpeg** on `PATH`
- **Claude subscription + Claude Code CLI** — the AI brain. Install from https://docs.claude.com/claude-code, then run `claude` once to authenticate.

Optional (each integration self-disables cleanly if missing):
- **GitHub CLI** (`gh auth login`) — powers the briefing's "recent commits" section
- **Gmail account with an app password** — powers briefing + check-in emails
- **Google Cloud OAuth2 Desktop client** — powers the calendar widget

### 1. Clone + install deps

```bash
git clone https://github.com/YOUR_USER/pam.git
cd pam
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env             # edit if you want to override defaults
```

### 2. Install Whisper (voice transcription)

```bash
./scripts/install_whisper.sh     # Windows: .\scripts\install_whisper.ps1
```

This clones [whisper.cpp](https://github.com/ggerganov/whisper.cpp), detects your accelerator (CUDA / Metal / CPU), builds `whisper-server`, and downloads the default model (~500 MB). Takes 2–10 minutes.

Override the model if you want a smaller one:
```bash
WHISPER_MODEL=ggml-base.en-q5_0.bin ./scripts/install_whisper.sh
```

### 3. Run

```bash
python -m app.main
```

PAM generates a self-signed SSL cert on first boot, seeds a few starter to-dos /
habits / kanban cards, starts the schedulers, and binds to `https://0.0.0.0:8400`.

Open **https://localhost:8400** and accept the self-signed cert warning (once per
browser).

### 4. Verify Claude

```bash
claude --print -p "say hello"
```

Must return text. If not, PAM's AI features will flag as broken via `GET /health`.

---

## Optional integrations

### Gmail (briefing + check-in emails)

1. In your Google Account → Security → **App passwords**, generate a 16-char password.
2. Create `data/email_credentials.json`:
   ```json
   {
     "email": "you@gmail.com",
     "app_password": "xxxx xxxx xxxx xxxx",
     "recipient": "you@gmail.com"
   }
   ```
3. Restart PAM. The briefing scheduler activates.

### Google Calendar

1. Create an OAuth2 **Desktop app** in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Calendar API**.
3. Download the client secret JSON → `data/google_credentials.json`.
4. Run the one-time auth flow:
   ```bash
   python -m app.services.google_auth
   ```
   This opens a browser for consent and writes `data/google_token.json`.
5. Restart PAM.

### GitHub commits in your daily briefing

1. Install `gh` CLI: https://cli.github.com/
2. `gh auth login`
3. Set `GITHUB_OWNER=your-github-username` in `.env`.
4. Restart PAM.

---

## Keep it running in the background

### systemd (Linux)
```bash
cp docs/pam.service.example /etc/systemd/system/pam.service
# edit user + paths
sudo systemctl daemon-reload
sudo systemctl enable --now pam
```

### launchd (macOS)
```bash
cp docs/com.pam.plist.example ~/Library/LaunchAgents/com.pam.plist
# edit user + paths
launchctl load ~/Library/LaunchAgents/com.pam.plist
```

### Windows
Use [nssm](https://nssm.cc/) or Task Scheduler, running `python -m app.main` from the repo root.

---

## Configuration reference

All config is environment-driven via `.env` (see `.env.example` for the full
surface). Runtime tweaks (schedule hours, SFX volume, timezone, email recipient)
are in the Settings page.

Key defaults:
- `PAM_PORT=8400`
- `PAM_DATA_DIR=./data`
- `WHISPER_BACKEND=auto`
- `DEFAULT_TIMEZONE=America/New_York`
- `DEFAULT_BRIEFING_HOUR=7`
- `DEFAULT_CHECKIN_HOUR=13`
- `DEFAULT_HABIT_RESET_HOUR=4`

---

## Architecture

```
                     ┌──────────────────────────────────┐
                     │   Browser (desktop + mobile)     │
                     │   vanilla JS SPA — no build step │
                     └──────────────┬───────────────────┘
                                    │ HTTPS (self-signed)
                                    ▼
     ┌──────────────────────────────────────────────────────┐
     │              FastAPI / uvicorn                       │
     │   Routers  →  Services  →  Schedulers  →  Settings   │
     └───┬─────────────┬────────────┬──────────────┬────────┘
         │             │            │              │
         ▼             ▼            ▼              ▼
    ┌────────┐   ┌──────────┐  ┌──────────┐  ┌────────────┐
    │ SQLite │   │ Claude   │  │ Whisper  │  │ Optional:  │
    │ (single│   │ Code CLI │  │ server   │  │ Gmail SMTP │
    │ file)  │   │          │  │ (local)  │  │ Google Cal │
    └────────┘   └──────────┘  └──────────┘  │ GitHub CLI │
                                             └────────────┘
```

- **No auth**: single-user, trusted-network only.
- **No Postgres**: SQLite single-file, idempotent `CREATE TABLE IF NOT EXISTS` on boot.
- **No RAG**: Claude gets fresh context every call. Settings/memory live in SQLite.
- **Three schedulers** run inside the FastAPI lifespan (briefing / check-in / habit reset). They re-read their hour from the Settings page each loop iteration — no restart needed when you change schedules.

Full layout and contributing guide: see [`CLAUDE.md`](CLAUDE.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## What's intentionally out of scope

- Multi-user / per-user isolation
- Remote-exposed installs with auth (if you need this, reverse-proxy behind Cloudflare Access / Tailscale / whatever)
- Mobile native apps (the web UI is mobile-responsive)
- Non-Claude AI backends (on the v2 roadmap — `AI_BACKEND=api` for direct Anthropic API)
- Vector DBs / RAG
- Hosted SaaS version

---

## Troubleshooting

- **Mic button greyed out** — your browser needs HTTPS on a non-localhost origin. PAM's auto-generated cert should handle this; if not, run `./scripts/generate_cert.sh`.
- **"Whisper binary not found"** — run `./scripts/install_whisper.sh`. The first run takes a while to build + download the model.
- **Briefing returns empty / no AI** — check `claude --print -p "hi"` on the host. If it fails, the CLI isn't set up.
- **`GET /health`** returns per-integration status — use this to diagnose what's wired and what isn't.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version: small PRs, keep the
single-user / Claude-first / SQLite-only assumptions, don't re-introduce
platform-specific subprocess flags without a guard.

---

## License

MIT — see [`LICENSE`](LICENSE). Third-party dependency licenses: [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
