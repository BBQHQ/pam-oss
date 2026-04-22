"""Whisper transcription service — manages whisper.cpp server process with TTL."""

import asyncio
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
from app.config import (
    WHISPER_SERVER_EXE,
    WHISPER_MODEL_PATH,
    WHISPER_HOST,
    WHISPER_PORT,
    WHISPER_THREADS,
    WHISPER_TTL_SECONDS,
)

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_last_used: float = 0.0
_server_process: subprocess.Popen | None = None
_ttl_task: asyncio.Task | None = None
_base_url = f"http://{WHISPER_HOST}:{WHISPER_PORT}"


async def _is_server_running() -> bool:
    """Check if whisper-server is responding."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(_base_url, timeout=3)
            return resp.status_code == 200
    except Exception:
        return False


async def _start_server() -> bool:
    """Start the whisper-server process."""
    global _server_process

    if await _is_server_running():
        return True

    # Kill any orphaned process
    if _server_process and _server_process.poll() is None:
        _server_process.terminate()
        _server_process.wait(timeout=5)

    if not WHISPER_SERVER_EXE.exists():
        print(f"[PAM] Whisper binary not found at {WHISPER_SERVER_EXE}")
        print("[PAM] Run scripts/install_whisper.sh (or .ps1) to build it.")
        return False
    if not WHISPER_MODEL_PATH.exists():
        print(f"[PAM] Whisper model not found at {WHISPER_MODEL_PATH}")
        return False

    try:
        _server_process = subprocess.Popen(
            [
                str(WHISPER_SERVER_EXE),
                "-m", str(WHISPER_MODEL_PATH),
                "-t", str(WHISPER_THREADS),
                "--host", WHISPER_HOST,
                "--port", str(WHISPER_PORT),
            ],
            cwd=str(WHISPER_SERVER_EXE.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATION_FLAGS,
        )
    except Exception as e:
        print(f"[PAM] Failed to start whisper-server: {e}")
        return False

    # Wait for server to be ready (model loading takes a few seconds)
    for _ in range(30):
        await asyncio.sleep(1)
        if await _is_server_running():
            print("[PAM] Whisper server started")
            return True

    print("[PAM] Whisper server failed to start in time")
    return False


async def _stop_server():
    """Stop the whisper-server process."""
    global _server_process

    if _server_process and _server_process.poll() is None:
        _server_process.terminate()
        try:
            _server_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _server_process.kill()
        print("[PAM] Whisper server stopped")

    _server_process = None


async def _ttl_watcher():
    """Background task that stops the server after idle timeout."""
    while True:
        await asyncio.sleep(30)
        if _last_used > 0 and _server_process and _server_process.poll() is None:
            idle = time.time() - _last_used
            if idle > WHISPER_TTL_SECONDS:
                print(f"[PAM] Whisper idle for {idle:.0f}s — stopping server")
                await _stop_server()


def start_ttl_watcher():
    """Start the TTL background watcher. Call once at app startup."""
    global _ttl_task
    if _ttl_task is None:
        _ttl_task = asyncio.create_task(_ttl_watcher())


def _convert_to_wav(audio_bytes: bytes, filename: str) -> bytes:
    """Convert any audio format to 16kHz mono WAV using ffmpeg."""
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(audio_bytes)
        src_path = src.name
    out_path = src_path + ".wav"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", src_path,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                out_path,
            ],
            capture_output=True,
            timeout=30,
            creationflags=_CREATION_FLAGS,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        Path(src_path).unlink(missing_ok=True)
        Path(out_path).unlink(missing_ok=True)


async def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> dict:
    """Transcribe audio bytes via whisper.cpp server.

    Returns {"text": "...", "duration_ms": ...}
    """
    global _last_used

    # Ensure server is running
    running = await _is_server_running()
    if not running:
        started = await _start_server()
        if not started:
            return {"error": "Failed to start whisper server. Check that whisper-server.exe and model file exist."}

    _last_used = time.time()
    start = time.time()

    # Convert to WAV — whisper.cpp only accepts WAV
    try:
        wav_bytes = await asyncio.to_thread(_convert_to_wav, audio_bytes, filename)
    except Exception as e:
        return {"error": f"Audio conversion failed: {str(e)}"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_base_url}/inference",
                files={"file": ("audio.wav", wav_bytes)},
                data={"response_format": "json"},
                timeout=120,
            )
            elapsed_ms = int((time.time() - start) * 1000)

            if resp.status_code == 200:
                result = resp.json()
                # Whisper emits a newline after every segment; collapse all
                # whitespace runs to single spaces so mid-thought segment
                # boundaries don't render as line breaks.
                text = " ".join((result.get("text") or "").split())
                return {
                    "text": text,
                    "duration_ms": elapsed_ms,
                }
            else:
                return {"error": f"Whisper server returned {resp.status_code}: {resp.text}"}
    except httpx.TimeoutException:
        return {"error": "Transcription timed out (120s limit)"}
    except Exception as e:
        return {"error": f"Transcription failed: {str(e)}"}


async def warm_up() -> dict:
    """Start whisper server without blocking. Returns immediately.

    Also bumps _last_used so the TTL watcher won't kill the server while
    a recording is in progress (frontend heartbeats this during recording).
    """
    global _last_used
    _last_used = time.time()
    running = await _is_server_running()
    if running:
        return {"status": "already_running"}
    # Fire off server start in background — don't await full readiness
    asyncio.create_task(_start_server())
    return {"status": "warming_up"}


async def get_status() -> dict:
    """Return current whisper service status."""
    running = await _is_server_running()
    idle = time.time() - _last_used if _last_used > 0 else None
    return {
        "running": running,
        "idle_seconds": round(idle) if idle else None,
        "ttl_seconds": WHISPER_TTL_SECONDS,
    }
