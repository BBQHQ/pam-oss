# Updating PAM

How to pull the latest changes into an existing PAM install.

## TL;DR (the normal case)

From your PAM folder:

```
git pull
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Then **hard-refresh your browser** (Ctrl+Shift+R / Cmd+Shift+R) so it drops the cached `pam.js` and `pam.css`. Without this you'll see stale UI.

That's the whole update path 95% of the time.

## What migrates automatically

On restart:
- New SQLite tables auto-create via `CREATE TABLE IF NOT EXISTS`.
- New settings keys resolve from code defaults — no DB rows needed until you change them.
- Existing settings, notes, todos, habits, gratitude tiles, SFX uploads, SSL certs — all preserved.

## What doesn't migrate automatically

Default seed data only runs when a table is **empty**. If a release changes defaults (e.g., gratitude pillars, starter todos), existing rows stay as they were.

To pick up new defaults, nuke the relevant table and let it re-seed:

```
# stop PAM first (Ctrl+C)
sqlite3 data/notes.db "DELETE FROM gratitude;"
python -m app.main
```

You lose customizations on those tiles, but they re-seed clean. Works the same for `todos`, `kanban_cards`, etc.

No `sqlite3` on PATH? Open `data/notes.db` in [DB Browser for SQLite](https://sqlitebrowser.org/), run the same SQL, save.

## Troubleshooting

- **UI looks stale** — hard-refresh. Browsers cache aggressively.
- **`ModuleNotFoundError`** — you skipped `pip install -r requirements.txt`. New releases may add Python deps.
- **`GET /health`** shows per-integration status. First stop when something's off.
- **Want to see what changed?** `git log --oneline HEAD@{1}..HEAD` between pulls.

---

## Advanced: re-cloning from scratch (dev workflow)

If you're iterating on PAM and want to periodically re-clone to test the cold-install experience, symlink expensive artifacts out of the clone so they survive resets.

**One-time setup** — stash the model and your `.env` in a stable cache location:

```powershell
mkdir C:\pam-cache
move whisper C:\pam-cache\whisper
copy .env C:\pam-cache\.env
```

**Every re-clone** (~90 seconds vs. 10+ minutes cold):

```powershell
git clone https://github.com/BBQHQ/pam-oss.git
cd pam-oss\pam
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cmd /c mklink /J whisper C:\pam-cache\whisper
copy C:\pam-cache\.env .env
python -m app.main
```

Want to preserve your data across clones too? Add `data/` to the cache the same way:

```powershell
move data C:\pam-cache\data
# then each re-clone:
cmd /c mklink /J data C:\pam-cache\data
```

Or leave `data/` out of the cache for a true fresh-state install every time.

**Why this works**: pip caches wheels globally so `pip install` is near-instant after the first run. Whisper's 500MB model is the slow download — symlinking makes it persistent. Everything else regenerates cheaply.
