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

> **Not a programmer?** Skip ahead to [Windows install for non-programmers](#windows-install-for-non-programmers) for a click-by-click walkthrough.

### Prerequisites

Required:
- **Python 3.11+**
- **git** — used by the Whisper installer to fetch whisper.cpp. You can download PAM itself as a ZIP if you prefer, but Git still needs to be installed for step 2.
- **ffmpeg** on `PATH`
- **Claude subscription + Claude Code CLI** — the AI brain. Install from https://docs.claude.com/claude-code, then run `claude` once to authenticate.

Optional (each integration self-disables cleanly if missing):
- **GitHub CLI** (`gh auth login`) — powers the briefing's "recent commits" section
- **Gmail account with an app password** — powers briefing + check-in emails
- **Google Cloud OAuth2 Desktop client** — powers the calendar widget

### 1. Get the code + install deps

Either clone with Git, or download the repo as a ZIP from GitHub (**Code → Download ZIP**) and unzip it. Then:

```bash
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

## Windows install for non-programmers

If you've never used a terminal before, follow these steps in order. You'll copy-paste a handful of commands — nothing to write from scratch.

### 1. Install the prerequisites

Install each of these with their default settings unless noted:

1. **Python 3.11 or newer** — [python.org/downloads](https://www.python.org/downloads/). **Important:** on the first installer screen, check the box **"Add Python to PATH"** before clicking Install.
2. **Git** — [git-scm.com/downloads](https://git-scm.com/downloads). Accept all defaults. (You don't have to use Git yourself, but PAM's voice-transcription installer uses it behind the scenes.)
3. **ffmpeg** — grab a Windows build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (the "release essentials" zip). Unzip it to `C:\ffmpeg`, then add `C:\ffmpeg\bin` to your system PATH. (Start menu → "Edit the system environment variables" → **Environment Variables** → under **System variables** pick **Path** → **Edit** → **New** → paste `C:\ffmpeg\bin` → OK everything.)
4. **Claude Code CLI** — follow [docs.claude.com/claude-code](https://docs.claude.com/claude-code). After installing, open PowerShell, type `claude`, and sign in with your Claude subscription.

Close and reopen any open terminals after installing so the PATH changes take effect.

### 2. Download the PAM code

Easiest way (no command line needed):
1. Go to the PAM GitHub page.
2. Click the green **Code** button → **Download ZIP**.
3. Unzip it somewhere you'll remember, like `C:\PAM`.

(If you're comfortable with Git, `git clone` works too — same result.)

### 3. Set up PAM's environment

You'll do this in a terminal window. Don't worry — you'll only type a few lines and you can copy them exactly.

**Open a terminal in the PAM folder:**
1. Open **File Explorer** and go to the PAM folder.
2. Click once in the address bar at the top, type `powershell`, and press **Enter**. A blue window opens, already pointing at the PAM folder.

**Create the virtual environment** (a private sandbox for PAM's parts):
```
python -m venv .venv
```
Wait 10–30 seconds for the prompt to come back. A `.venv` folder appears inside PAM.

**Activate it:**
```
.venv\Scripts\Activate.ps1
```
You'll know it worked because `(.venv)` appears at the start of your prompt.

> If PowerShell complains about "running scripts is disabled," paste this, press Enter, answer **Y**, then try activate again:
> ```
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

**Install PAM's parts:**
```
pip install -r requirements.txt
```
Text scrolls by for 1–3 minutes. When the prompt returns with no red error, it's done.

**Create the settings file:**
1. In File Explorer, find `.env.example` in the PAM folder.
2. Right-click → **Copy**, then right-click empty space → **Paste**. You'll get `.env.example - Copy`.
3. Rename the copy to exactly `.env` (leading dot, no `.txt` on the end).

You don't need to open or edit it — the defaults work.

### 4. Install Whisper (voice transcription)

In the same terminal (still showing `(.venv)`):
```
.\scripts\install_whisper.ps1
```
This downloads and builds the voice engine and fetches the speech model. 2–10 minutes.

### 5. Start PAM

```
python -m app.main
```

Open **https://localhost:8400** in your browser. You'll see a scary-looking "Your connection is not private" warning — that's expected because PAM made its own certificate. Click **Advanced** → **Continue to localhost**. You only do this once per browser.

### Leaving and coming back

If you close the terminal, you'll need to reopen it in the PAM folder (address bar → `powershell` → Enter) and run the activate line again before launching PAM:
```
.venv\Scripts\Activate.ps1
python -m app.main
```

To have PAM start automatically in the background, see [nssm](https://nssm.cc/) or Windows Task Scheduler.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version: small PRs, keep the
single-user / Claude-first / SQLite-only assumptions, don't re-introduce
platform-specific subprocess flags without a guard.

---

## License

MIT — see [`LICENSE`](LICENSE). Third-party dependency licenses: [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
