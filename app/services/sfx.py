"""Sound effects registry — per-pool MP3s + Myinstants ingest.

Sounds live on disk under `frontend/sounds/` (and `frontend/sounds/custom/` for
user uploads + URL ingest). The `sfx_sounds` SQLite table is the source of
truth for which file is in which pool, its display name, and whether it's
enabled. The frontend fetches the list and rotates randomly.
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import aiosqlite

from app.config import DATA_DIR, PAM_ROOT
from app.services.settings import SFX_POOLS

# Myinstants is fronted by Cloudflare which blocks plain httpx. curl_cffi
# impersonates a real Chrome TLS fingerprint and gets through.
try:
    from curl_cffi import requests as cffi_requests  # type: ignore
    _HAS_CFFI = True
except Exception:
    cffi_requests = None  # type: ignore
    _HAS_CFFI = False

DB_PATH = DATA_DIR / "notes.db"
SOUNDS_DIR = PAM_ROOT / "frontend" / "sounds"
CUSTOM_DIR = SOUNDS_DIR / "custom"
STATIC_PREFIX = "/static/sounds/"

MYINSTANTS_HOSTS = {"myinstants.com", "www.myinstants.com"}
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# OSS ships with no bundled MP3s (see OPEN_SOURCE_PLAN §17 — copyright audit).
# Users populate the pools via upload or Myinstants ingest; no seed map needed.
_SEED_POOLS: dict[str, tuple[str, ...]] = {}


def _pretty_name(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"-\d{4,}$", "", stem)  # trailing myinstants id
    return stem.replace("-", " ").replace("_", " ").strip().title()


async def _get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS sfx_sounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            pool TEXT NOT NULL,
            display_name TEXT NOT NULL,
            source_url TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created TEXT NOT NULL
        )
        """
    )
    await db.commit()
    return db


async def _ensure_seeded(db) -> None:
    """First-run: insert one row per MP3 named in `_SEED_POOLS` that exists on disk.

    OSS ships `_SEED_POOLS` empty, so this is a no-op unless a downstream fork
    populates it. Kept as a hook so forks can re-enable bundled seed data.
    """
    cursor = await db.execute("SELECT COUNT(*) AS n FROM sfx_sounds")
    row = await cursor.fetchone()
    if row["n"] > 0:
        return
    now = datetime.now().isoformat()
    for pool, files in _SEED_POOLS.items():
        for filename in files:
            if not (SOUNDS_DIR / filename).exists():
                continue
            await db.execute(
                "INSERT OR IGNORE INTO sfx_sounds "
                "(filename, pool, display_name, source_url, enabled, created) "
                "VALUES (?, ?, ?, NULL, 1, ?)",
                (filename, pool, _pretty_name(filename), now),
            )
    await db.commit()


async def list_sounds() -> list[dict]:
    db = await _get_db()
    try:
        await _ensure_seeded(db)
        cursor = await db.execute(
            "SELECT id, filename, pool, display_name, source_url, enabled, created "
            "FROM sfx_sounds ORDER BY pool, display_name"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    sounds = []
    for r in rows:
        is_custom = r["filename"].startswith("custom/") or r["source_url"] is not None
        url_path = STATIC_PREFIX + r["filename"]
        sounds.append(
            {
                "id": r["id"],
                "filename": r["filename"],
                "pool": r["pool"],
                "display_name": r["display_name"],
                "source_url": r["source_url"],
                "enabled": bool(r["enabled"]),
                "url": url_path,
                "is_custom": is_custom,
            }
        )
    return sounds


async def add_sound(
    filename: str, pool: str, display_name: str | None = None, source_url: str | None = None
) -> dict:
    if pool not in SFX_POOLS:
        raise ValueError(f"Unknown pool: {pool}")
    name = display_name or _pretty_name(filename)
    now = datetime.now().isoformat()
    db = await _get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO sfx_sounds "
            "(filename, pool, display_name, source_url, enabled, created) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (filename, pool, name, source_url, now),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT id FROM sfx_sounds WHERE filename = ?", (filename,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    return {
        "id": row["id"],
        "filename": filename,
        "pool": pool,
        "display_name": name,
        "source_url": source_url,
        "enabled": True,
        "url": STATIC_PREFIX + filename,
        "is_custom": filename.startswith("custom/") or source_url is not None,
    }


async def delete_sound(sound_id: int, *, remove_file: bool = True) -> bool:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT filename, source_url FROM sfx_sounds WHERE id = ?", (sound_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM sfx_sounds WHERE id = ?", (sound_id,))
        await db.commit()
    finally:
        await db.close()

    if remove_file and (row["source_url"] or row["filename"].startswith("custom/")):
        path = SOUNDS_DIR / row["filename"]
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    return True


async def update_sound(
    sound_id: int,
    *,
    enabled: bool | None = None,
    pool: str | None = None,
    display_name: str | None = None,
) -> bool:
    fields, values = [], []
    if enabled is not None:
        fields.append("enabled = ?")
        values.append(1 if enabled else 0)
    if pool is not None:
        if pool not in SFX_POOLS:
            raise ValueError(f"Unknown pool: {pool}")
        fields.append("pool = ?")
        values.append(pool)
    if display_name is not None:
        fields.append("display_name = ?")
        values.append(display_name.strip())
    if not fields:
        return False
    values.append(sound_id)
    db = await _get_db()
    try:
        cursor = await db.execute(
            f"UPDATE sfx_sounds SET {', '.join(fields)} WHERE id = ?", values
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ─── Myinstants ingest ───────────────────────────────────

_MP3_PATTERNS = (
    re.compile(r"""onmousedown\s*=\s*["']\s*play\(\s*["']([^"']+\.mp3)["']""", re.IGNORECASE),
    re.compile(r"""<meta\s+property=["']og:audio["']\s+content=["']([^"']+\.mp3)["']""", re.IGNORECASE),
    re.compile(r""""contentUrl"\s*:\s*"([^"]+\.mp3)\"""", re.IGNORECASE),
    re.compile(r"""(/media/sounds/[A-Za-z0-9_\-]+\.mp3)"""),
)


def _is_myinstants_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and parsed.netloc.lower() in MYINSTANTS_HOSTS
    except Exception:
        return False


def _fetch_myinstants(url: str) -> tuple[int, bytes, str]:
    """Blocking fetch via curl_cffi (Chrome TLS fingerprint) — runs in a thread."""
    if not _HAS_CFFI:
        raise RuntimeError(
            "curl_cffi is not installed — required to bypass Myinstants' Cloudflare protection."
        )
    resp = cffi_requests.get(
        url, impersonate="chrome120", headers=_BROWSER_HEADERS, timeout=20, allow_redirects=True
    )
    return resp.status_code, resp.content, resp.text


async def ingest_myinstants(page_url: str, pool: str) -> dict:
    """Scrape a Myinstants page, download the MP3, register it in the chosen pool."""
    if not _is_myinstants_url(page_url):
        raise ValueError("Only Myinstants URLs are supported.")
    if pool not in SFX_POOLS:
        raise ValueError(f"Unknown pool: {pool}")

    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)

    page_status, _, page_text = await asyncio.to_thread(_fetch_myinstants, page_url)
    if page_status != 200:
        raise RuntimeError(f"Myinstants page fetch failed (HTTP {page_status}).")

    mp3_path: str | None = None
    for pat in _MP3_PATTERNS:
        m = pat.search(page_text)
        if m:
            mp3_path = m.group(1)
            break
    if not mp3_path:
        raise RuntimeError(
            "Couldn't find an MP3 reference on that Myinstants page. "
            "If the page loads in a browser, the layout may have changed."
        )

    if mp3_path.startswith("/"):
        mp3_url = f"https://www.myinstants.com{mp3_path}"
    elif mp3_path.startswith("http"):
        mp3_url = mp3_path
    else:
        mp3_url = f"https://www.myinstants.com/{mp3_path.lstrip('/')}"

    mp3_status, mp3_bytes, _ = await asyncio.to_thread(_fetch_myinstants, mp3_url)
    if mp3_status != 200:
        raise RuntimeError(f"MP3 download failed (HTTP {mp3_status}).")

    raw_name = Path(urlparse(mp3_url).path).name
    safe_name = re.sub(r"[^A-Za-z0-9_.\-]", "_", raw_name) or "myinstants.mp3"
    target = CUSTOM_DIR / safe_name
    counter = 1
    while target.exists():
        target = CUSTOM_DIR / f"{target.stem}-{counter}{target.suffix}"
        counter += 1
    await asyncio.to_thread(target.write_bytes, mp3_bytes)

    rel = f"custom/{target.name}"
    return await add_sound(
        filename=rel,
        pool=pool,
        display_name=_pretty_name(target.name),
        source_url=page_url,
    )


async def save_uploaded_mp3(filename: str, content: bytes, pool: str) -> dict:
    if pool not in SFX_POOLS:
        raise ValueError(f"Unknown pool: {pool}")
    if not filename.lower().endswith(".mp3"):
        raise ValueError("Only .mp3 uploads are supported.")
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.\-]", "_", filename)
    target = CUSTOM_DIR / safe_name
    counter = 1
    while target.exists():
        target = CUSTOM_DIR / f"{target.stem}-{counter}{target.suffix}"
        counter += 1
    await asyncio.to_thread(target.write_bytes, content)
    return await add_sound(
        filename=f"custom/{target.name}",
        pool=pool,
        display_name=_pretty_name(target.name),
        source_url=None,
    )
