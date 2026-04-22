"""PAM — Personal Assistant Manager."""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import PAM_ROOT, settings
from app.services.whisper import start_ttl_watcher
from app.services.project_registry import load_projects
from app.services.bootstrap import ensure_certs, seed_starter_data
from app.routers import (
    voice, tasks, projects, todos, notes, questions,
    settings as settings_router,
    sfx, portraits as portraits_router,
    briefing, calendar, kanban, accomplishments, prompt_zone, gratitude,
)
from app.services import portraits as portraits_service


async def _run_at_hour(label: str, hour_key: str, hour_default: int, action):
    """Generic hour-of-day scheduler. Re-reads the hour from settings each tick."""
    from datetime import datetime, timedelta
    from app.services.settings import get_setting

    print(f"[PAM] {label} scheduler started (hour key: {hour_key})")
    while True:
        hour = await get_setting(hour_key, hour_default)
        now = datetime.now()
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        try:
            await action()
        except Exception as e:
            print(f"[PAM] {label} failed: {e}")


async def _briefing_scheduler():
    from app.services.email import is_configured
    from app.services.briefing import send_briefing_email
    if not is_configured():
        print("[PAM] Email not configured — briefing scheduler disabled")
        return
    await _run_at_hour("Briefing", "briefing_hour", settings.default_briefing_hour, send_briefing_email)


async def _habit_reset_scheduler():
    from app.services.todos import reset_habits

    async def action():
        await reset_habits()
        print("[PAM] Habits reset complete")

    await _run_at_hour("Habit reset", "habit_reset_hour", settings.default_habit_reset_hour, action)


async def _checkin_scheduler():
    from app.services.email import is_configured
    from app.services.briefing import send_checkin_email
    if not is_configured():
        print("[PAM] Email not configured — check-in scheduler disabled")
        return
    await _run_at_hour("Check-in", "checkin_hour", settings.default_checkin_hour, send_checkin_email)


def _quiet_conn_reset(loop, context):
    """Swallow harmless ConnectionResetError from Windows Proactor event loop.

    On Windows + Python 3.12+, uvicorn's ProactorEventLoop logs a traceback
    whenever a browser closes a polling connection with RST instead of FIN
    (e.g., fast /voice/status polling). The request itself completes fine;
    only the cleanup path on connection_lost trips. Silent on other platforms.
    """
    exc = context.get("exception")
    if isinstance(exc, ConnectionResetError):
        return
    loop.default_exception_handler(context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.get_event_loop().set_exception_handler(_quiet_conn_reset)
    ensure_certs()
    await seed_starter_data()
    load_projects()
    start_ttl_watcher()
    asyncio.create_task(_briefing_scheduler())
    asyncio.create_task(_habit_reset_scheduler())
    asyncio.create_task(_checkin_scheduler())
    yield


app = FastAPI(title="PAM", version="0.1.0", lifespan=lifespan)

# Routers
app.include_router(voice.router)
app.include_router(todos.router)
app.include_router(tasks.router)
app.include_router(notes.router)
app.include_router(questions.router)
app.include_router(projects.router)
app.include_router(settings_router.router)
app.include_router(sfx.router)
app.include_router(portraits_router.router)
app.include_router(briefing.router)
app.include_router(calendar.router)
app.include_router(kanban.router)
app.include_router(accomplishments.router)
app.include_router(prompt_zone.router)
app.include_router(gratitude.router)

# Static files
frontend_dir = PAM_ROOT / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
img_dir = PAM_ROOT / "img"
if img_dir.exists():
    app.mount("/img", StaticFiles(directory=str(img_dir)), name="img")
# User-uploaded custom assets (portraits, future extensions) live under data/custom/
# so they survive re-clones when data/ is preserved.
from app.config import DATA_DIR as _DATA_DIR
_custom_dir = _DATA_DIR / "custom"
_custom_dir.mkdir(parents=True, exist_ok=True)
app.mount("/custom", StaticFiles(directory=str(_custom_dir)), name="custom")


@app.get("/portraits")
async def list_portraits():
    """Return portraits grouped by time of day.

    Built-in portraits under /img/<period>/ are merged with user-uploaded
    portraits from data/custom/portraits/<period>/. Supports common image
    extensions (png, jpg, jpeg, webp, gif).
    """
    buckets = {}
    custom_urls = await portraits_service.list_urls_by_period()
    exts = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif")
    for period in ("morning", "workday", "evening"):
        items: list[str] = []
        d = img_dir / period
        if d.exists():
            found: list[str] = []
            for pattern in exts:
                found.extend(f"/img/{period}/{p.name}" for p in d.glob(pattern))
            items.extend(sorted(found))
        items.extend(custom_urls.get(period, []))
        buckets[period] = items
    return buckets


@app.get("/")
async def index():
    return FileResponse(str(frontend_dir / "index.html"))


@app.get("/health")
async def health():
    """Detailed health: per-integration status so the UI can show banners."""
    from app.services import claude_cli
    from app.services.email import is_configured as email_configured
    from app.services.whisper import get_status as whisper_status
    import shutil

    return {
        "status": "ok",
        "service": "PAM",
        "version": "0.1.0",
        "integrations": {
            "claude_cli": await claude_cli.health(),
            "whisper": await whisper_status(),
            "email": "ok" if email_configured() else "not_configured",
            "gh": "ok" if shutil.which(settings.gh_bin) else "not_installed",
        },
    }


def main():
    """Entry point for `python -m app.main` / `pam` console script."""
    import uvicorn
    cert = settings.ssl_cert_file
    key = settings.ssl_key_file
    # Make sure certs exist before uvicorn binds to them
    if settings.ssl_auto_generate:
        ensure_certs()
    # Port can be overridden at runtime via Settings UI (stored in notes.db).
    # Falls back to config.pam_port (from .env or default).
    port = settings.pam_port
    try:
        from app.services.settings import get_setting
        override = asyncio.run(get_setting("pam_port", settings.pam_port))
        if isinstance(override, int) and 1024 <= override <= 65535:
            port = override
    except Exception:
        pass
    kwargs = dict(host=settings.pam_host, port=port)
    if cert.exists() and key.exists():
        kwargs["ssl_certfile"] = str(cert)
        kwargs["ssl_keyfile"] = str(key)
    uvicorn.run("app.main:app", **kwargs)


if __name__ == "__main__":
    main()
