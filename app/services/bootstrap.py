"""PAM first-boot bootstrap — SSL cert generation and starter data seeding.

Both helpers are idempotent and safe to call on every boot.
"""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.config import DATA_DIR, settings


# ─── SSL cert auto-generation ─────────────────────

def ensure_certs() -> bool:
    """Generate a self-signed cert at the configured paths if missing.

    Returns True if certs now exist, False if generation failed.
    """
    cert = settings.ssl_cert_file
    key = settings.ssl_key_file

    if cert.exists() and key.exists():
        return True

    if not settings.ssl_auto_generate:
        print(f"[PAM] SSL certs missing and auto-generate disabled ({cert}, {key})")
        return False

    cert.parent.mkdir(parents=True, exist_ok=True)
    key.parent.mkdir(parents=True, exist_ok=True)

    # Prefer openssl CLI if available (fast, well-tested)
    if shutil.which("openssl"):
        try:
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:4096", "-nodes",
                    "-out", str(cert), "-keyout", str(key),
                    "-days", "3650",
                    "-subj", "/CN=localhost",
                ],
                check=True, capture_output=True, timeout=30,
            )
            print(f"[PAM] Generated self-signed SSL cert (openssl), valid 10 years: {cert}")
            return True
        except Exception as e:
            print(f"[PAM] openssl cert generation failed, falling back to Python: {e}")

    # Pure-Python fallback using `cryptography`
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timedelta, timezone

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        cert_obj = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )
        key.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cert.write_bytes(cert_obj.public_bytes(serialization.Encoding.PEM))
        print(f"[PAM] Generated self-signed SSL cert (cryptography), valid 10 years: {cert}")
        return True
    except Exception as e:
        print(f"[PAM] Cert generation failed completely: {e}")
        print("[PAM] Voice features require HTTPS on non-localhost origins.")
        print("[PAM] Either run scripts/generate_cert.sh or access PAM at http://localhost only.")
        return False


# ─── Starter data seeding ─────────────────────────

STARTER_TODOS = [
    "Take a look around",
    "Add your first real todo",
    "Pin a note on the Notes page",
    "Try recording a voice memo",
    "Delete these starter todos when you're ready",
]

STARTER_HABITS = [
    "Drink water",
    "Move your body",
    "Check in with yourself",
]

STARTER_KANBAN_BOARD = "Getting Started"
STARTER_KANBAN_CARDS = [
    "Explore PAM's features",
    "Set up Claude + Whisper",
    "Connect optional integrations (Gmail / Calendar / GitHub)",
]


async def seed_starter_data():
    """Insert starter todos/habits/kanban only if the DB is pristine."""
    if not settings.seed_starter_data:
        return

    db_path = DATA_DIR / "notes.db"
    now = datetime.now().isoformat()

    async with aiosqlite.connect(str(db_path)) as db:
        # Let service modules create their tables first. These CREATE TABLE
        # statements mirror what the services declare, so running this before
        # the services have ever been imported is still safe.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL,
                completed TEXT,
                category TEXT,
                parent_id INTEGER,
                recurrence TEXT,
                recurrence_days TEXT,
                streak_current INTEGER DEFAULT 0,
                streak_best INTEGER DEFAULT 0,
                last_reset TEXT,
                completion_count INTEGER DEFAULT 0,
                week_count INTEGER DEFAULT 0,
                last_week TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kanban_boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kanban_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL,
                column_name TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            )
        """)
        await db.commit()

        cursor = await db.execute("SELECT COUNT(*) FROM todos")
        todo_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM kanban_cards")
        card_count = (await cursor.fetchone())[0]

        if todo_count == 0:
            for text in STARTER_TODOS:
                await db.execute(
                    "INSERT INTO todos (text, created) VALUES (?, ?)",
                    (text, now),
                )
            for text in STARTER_HABITS:
                await db.execute(
                    "INSERT INTO todos (text, created, recurrence) VALUES (?, ?, 'daily')",
                    (text, now),
                )
            print(f"[PAM] Seeded {len(STARTER_TODOS)} starter todos + {len(STARTER_HABITS)} starter habits")

        if card_count == 0:
            cursor = await db.execute(
                "INSERT INTO kanban_boards (name, created) VALUES (?, ?)",
                (STARTER_KANBAN_BOARD, now),
            )
            board_id = cursor.lastrowid
            for i, title in enumerate(STARTER_KANBAN_CARDS):
                await db.execute(
                    "INSERT INTO kanban_cards (board_id, column_name, title, sort_order, created, updated) "
                    "VALUES (?, 'Backlog', ?, ?, ?, ?)",
                    (board_id, title, i, now, now),
                )
            print(f"[PAM] Seeded '{STARTER_KANBAN_BOARD}' kanban board with {len(STARTER_KANBAN_CARDS)} cards")

        await db.commit()
