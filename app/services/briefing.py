"""PAM Daily Briefing — assemble status data, generate summary, send email."""

import asyncio
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from app.config import DATA_DIR, GH_BIN, GITHUB_OWNER

BRIEFING_CACHE = DATA_DIR / "briefing.json"

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


async def _get_recent_commits(hours: int = 24) -> list[dict]:
    """Fetch recent commits across the configured GitHub owner's repos via GitHub CLI.

    Silently returns [] if gh CLI is not installed or no GITHUB_OWNER is configured.
    """
    gh = shutil.which(GH_BIN)
    if not gh or not GITHUB_OWNER:
        return []

    since_dt = datetime.now() - timedelta(hours=hours)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    since_push = since_dt.strftime("%Y-%m-%d")
    commits = []

    try:
        # Step 1: Find all repos pushed to recently
        result = await asyncio.to_thread(
            subprocess.run,
            [gh, "api",
             f"search/repositories?q=user:{GITHUB_OWNER}+pushed:>={since_push}&per_page=30",
             "--jq", ".items[].name"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8",
            creationflags=_CREATION_FLAGS,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return commits

        repos = [r.strip() for r in result.stdout.strip().split("\n") if r.strip()]

        # Step 2: Fetch recent commits from each repo
        for repo in repos:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [gh, "api",
                     f"repos/{GITHUB_OWNER}/{repo}/commits?since={since_iso}&per_page=15",
                     "--jq", ".[].commit.message"],
                    capture_output=True, text=True, timeout=10,
                    encoding="utf-8",
                    creationflags=_CREATION_FLAGS,
                )
                if result.returncode == 0 and result.stdout.strip():
                    for msg in result.stdout.strip().split("\n"):
                        msg = msg.strip()
                        if msg:
                            # Take first line of commit message only
                            first_line = msg.split("\n")[0][:120]
                            commits.append({"project": repo, "message": first_line})
            except Exception:
                pass

    except Exception:
        pass

    return commits


async def build_briefing_data() -> dict:
    """Gather all data for the daily briefing from existing services."""
    from app.services.todos import get_todos
    from app.services.task_engine import get_tasks
    from app.services.questions import get_open_questions
    from app.services.notes import get_notes
    from app.services.kanban import get_boards_summary, get_stale_cards
    from app.services.accomplishments import list_accomplishments, count_recent
    from app.services.voice_log import get_history as get_voice_history, get_count as get_voice_count
    from app.services.calendar import get_upcoming
    from app.services.todos import get_habit_summary
    from app.services.gratitude import get_gratitude_summary

    now = datetime.now()

    # Todos
    todos = await get_todos(show_done=False)
    todo_items = []
    stale_todos = 0
    for t in todos:
        age_days = (now - datetime.fromisoformat(t.created)).days
        todo_items.append({"text": t.text, "age_days": age_days})
        if age_days >= 7:
            stale_todos += 1

    # Tasks
    staged = get_tasks(status="staged")
    queued = get_tasks(status="queued")
    executing = get_tasks(status="executing")
    stale_tasks = sum(1 for t in queued if (now - datetime.fromisoformat(t.created)).days >= 3)

    # Questions
    questions = await get_open_questions()
    stale_questions = sum(
        1 for q in questions
        if (now - datetime.fromisoformat(q["created"])).days >= 2
    )

    # Pinned notes
    pinned = await get_notes(pinned=True)
    stale_notes = sum(1 for n in pinned if n.get("enhancement_stale"))

    # Accomplishments — last 24h and last 7d
    since_24h = (now - timedelta(hours=24)).isoformat()
    since_7d = (now - timedelta(days=7)).isoformat()
    accomp_24h = await list_accomplishments(limit=50, since=since_24h)
    accomp_7d_count = await count_recent(days=7)

    # Git commits — last 24h across all projects
    recent_commits = await _get_recent_commits(hours=24)

    # Voice transcriptions — last 24h
    voice_all = await get_voice_history(limit=50, offset=0)
    voice_24h = [v for v in voice_all
                 if datetime.fromisoformat(v["created_at"]) >= now - timedelta(hours=24)]
    voice_total = await get_voice_count()

    # Calendar — upcoming events
    try:
        upcoming_events = await get_upcoming(max_results=8)
    except Exception:
        upcoming_events = []

    # Habits
    try:
        habit_data = await get_habit_summary()
    except Exception:
        habit_data = {"today_done": 0, "today_total": 0, "active_streaks": [], "habits": [], "label": ""}

    # Gratitude
    try:
        gratitude_data = await get_gratitude_summary()
    except Exception:
        gratitude_data = {"pillars": [], "progress": {}}

    return {
        "todos": {
            "open": len(todo_items),
            "stale": stale_todos,
            "items": todo_items[:10],
        },
        "tasks": {
            "staged": len(staged),
            "queued": len(queued),
            "executing": len(executing),
            "stale_queued": stale_tasks,
            "staged_items": [{"title": t.title, "project": t.project} for t in staged[:5]],
            "queued_items": [{"title": t.title, "project": t.project} for t in queued[:5]],
        },
        "questions": {
            "open": len(questions),
            "stale": stale_questions,
            "items": [{"question": q["question"][:100], "context": q.get("context", "")} for q in questions[:5]],
        },
        "notes": {
            "pinned": len(pinned),
            "stale_enhancements": stale_notes,
        },
        "kanban": {
            "boards": await get_boards_summary(),
            "stale_count": len(await get_stale_cards()),
            "stale_items": [
                {"title": s["title"], "board": s["board"], "stale_days": s["stale_days"]}
                for s in (await get_stale_cards())[:5]
            ],
        },
        "accomplishments": {
            "last_24h_count": len(accomp_24h),
            "last_7d_count": accomp_7d_count,
            "recent_items": [
                {"text": a["text"], "source": a["source"], "completed_at": a["completed_at"]}
                for a in accomp_24h[:10]
            ],
        },
        "commits": {
            "last_24h_count": len(recent_commits),
            "items": recent_commits[:20],
        },
        "voice": {
            "last_24h_count": len(voice_24h),
            "total": voice_total,
            "recent_items": [
                {"text": v["text"][:120], "created_at": v["created_at"]}
                for v in voice_24h[:8]
            ],
        },
        "calendar": {
            "upcoming_count": len(upcoming_events),
            "items": [
                {"summary": e.get("summary", "Untitled"), "start": e.get("start", ""),
                 "end": e.get("end", "")}
                for e in upcoming_events[:8]
            ],
        },
        "habits": habit_data,
        "gratitude": gratitude_data,
        "generated_at": now.isoformat(),
    }


async def build_briefing_summary(data: dict) -> str:
    """Send briefing data to Claude CLI for a natural-language summary."""
    # Build a concise data dump for Claude
    lines = []
    lines.append(f"Open to-dos: {data['todos']['open']} ({data['todos']['stale']} older than 7 days)")
    if data['todos']['items']:
        for item in data['todos']['items'][:5]:
            lines.append(f"  - {item['text']} ({item['age_days']}d old)")

    lines.append(f"Tasks needing approval: {data['tasks']['staged']}")
    for t in data['tasks']['staged_items']:
        proj = f" [{t['project']}]" if t['project'] else ""
        lines.append(f"  - {t['title']}{proj}")

    lines.append(f"Queued tasks: {data['tasks']['queued']} ({data['tasks']['stale_queued']} stuck 3+ days)")
    lines.append(f"Executing: {data['tasks']['executing']}")

    lines.append(f"Open PAM questions: {data['questions']['open']} ({data['questions']['stale']} unanswered 2+ days)")
    for q in data['questions']['items']:
        lines.append(f"  - {q['question']}")

    lines.append(f"Pinned notes: {data['notes']['pinned']} ({data['notes']['stale_enhancements']} with stale enhancements)")

    # Recent wins — feed these prominently into the briefing
    accomp = data.get("accomplishments", {})
    lines.append(
        f"\nRECENT WINS — {accomp.get('last_24h_count', 0)} in last 24h, "
        f"{accomp.get('last_7d_count', 0)} in last 7 days"
    )
    for a in accomp.get("recent_items", []):
        lines.append(f"  ✓ {a['text']} [{a['source']}]")

    # Git commits — shipped code
    commits = data.get("commits", {})
    if commits.get("last_24h_count", 0) > 0:
        lines.append(f"\nGIT COMMITS — {commits['last_24h_count']} in last 24h")
        for c in commits.get("items", []):
            lines.append(f"  [{c['project']}] {c['message']}")

    # Voice transcriptions — PAM interactions
    voice = data.get("voice", {})
    if voice.get("last_24h_count", 0) > 0:
        lines.append(f"\nVOICE MEMOS — {voice['last_24h_count']} in last 24h ({voice.get('total', 0)} total)")
        for v in voice.get("recent_items", []):
            lines.append(f"  - {v['text']}")

    # Calendar — what's coming up
    cal = data.get("calendar", {})
    if cal.get("upcoming_count", 0) > 0:
        lines.append(f"\nUPCOMING EVENTS — {cal['upcoming_count']}")
        for e in cal.get("items", []):
            lines.append(f"  - {e['summary']} ({e['start']})")

    # Habits
    habits = data.get("habits", {})
    if habits.get("today_total", 0) > 0:
        lines.append(f"\nHABITS — {habits['today_done']}/{habits['today_total']} done today")
        for h in habits.get("habits", []):
            status = "done" if h.get("done") else "pending"
            streak_info = f" (streak: {h.get('streak_current', 0)}d"
            if h.get("streak_best", 0) > h.get("streak_current", 0):
                streak_info += f", best: {h['streak_best']}d"
            streak_info += ")"
            lines.append(f"  {'✓' if h.get('done') else '○'} {h['text']}: {status}{streak_info}")
        for s in habits.get("active_streaks", []):
            if s["current"] >= 3:
                best_note = " — personal best!" if s["current"] >= s["best"] else ""
                lines.append(f"  🔥 {s['text']}: {s['current']}-day streak{best_note}")

    # Gratitude pillars
    gratitude = data.get("gratitude", {})
    if gratitude.get("pillars"):
        lines.append(f"\nGRATITUDE PILLARS — {', '.join(gratitude['pillars'])}")
        for title, label in gratitude.get("progress", {}).items():
            if label:
                lines.append(f"  {title}: {label}")

    # Kanban boards
    if data.get("kanban"):
        for b in data["kanban"]["boards"]:
            cols = b.get("columns", {})
            total = sum(cols.values())
            if total > 0:
                in_prog = cols.get("in_progress", 0)
                backlog = cols.get("backlog", 0)
                lines.append(f"Kanban {b['label']}: {total} cards ({backlog} backlog, {in_prog} in progress)")
        stale_count = data["kanban"]["stale_count"]
        if stale_count > 0:
            lines.append(f"  Stale cards (in progress 14+ days): {stale_count}")
            for s in data["kanban"]["stale_items"][:3]:
                lines.append(f"    - {s['title']} ({s['stale_days']}d stale)")

    data_text = "\n".join(lines)

    prompt = (
        "You are PAM, a personal executive assistant. Generate a brief daily briefing for the user. "
        "Be concise and actionable. Structure the briefing with FOUR clear parts:\n"
        "  1) **Recent wins** — open with what the user has actually accomplished recently. "
        "Be warm, specific, an attaboy. Reference concrete items from the RECENT WINS list, "
        "GIT COMMITS (shipped code across projects), and VOICE MEMOS (ideas/notes dictated). "
        "Commits are strong evidence of real work — highlight them. "
        "If there are no recent wins or commits, gently note that.\n"
        "  2) **Habits check-in** — celebrate active streaks with specifics (e.g. '12-day workout streak "
        "is your longest ever'). Gently note at-risk streaks as motivation, not guilt. If a streak broke, "
        "mention it once as 'today is a fresh start' — never list multiple missed days. "
        "Show today's progress (e.g. '3/5 habits done').\n"
        "  3) **Gratitude note** — close the positive section with a brief, grounded gratitude note. "
        "Reference one specific pillar from the GRATITUDE PILLARS list (family, health, home, etc.) "
        "and one concrete progress metric. Keep it real and tangible, not fluffy or generic. "
        "This should feel like evidence that things are going well.\n"
        "  4) **What's ahead** — then move to upcoming calendar events, what needs attention, "
        "what's going stale, and suggested priorities. Include upcoming events if any.\n\n"
        "The briefing should feel grounded in real progress, not just a forward-looking task dump. "
        "Use markdown formatting. Keep it under 350 words. Don't be overly formal or robotic.\n\n"
        f"Current date: {datetime.now().strftime('%A, %B %d, %Y')}\n\n"
        f"Status:\n{data_text}"
    )

    from app.services.claude_cli import run_claude
    result = await run_claude(prompt, timeout=60)
    if result["ok"] and result["text"]:
        return result["text"]
    if result.get("error"):
        print(f"[PAM] Briefing Claude call failed: {result['error']}")

    # Fallback: return the raw data as formatted text
    return f"## Daily Status\n\n{data_text}"


async def generate_briefing() -> dict:
    """Generate a fresh briefing and cache it."""
    data = await build_briefing_data()
    summary = await build_briefing_summary(data)

    result = {
        "summary": summary,
        "data": data,
        "generated_at": data["generated_at"],
    }

    # Cache
    try:
        BRIEFING_CACHE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[PAM] Failed to cache briefing: {e}")

    return result


def get_cached_briefing() -> dict | None:
    """Return cached briefing if it was generated today."""
    try:
        if not BRIEFING_CACHE.exists():
            return None
        cached = json.loads(BRIEFING_CACHE.read_text(encoding="utf-8"))
        gen_date = datetime.fromisoformat(cached["generated_at"]).date()
        if gen_date == datetime.now().date():
            return cached
        return None
    except Exception:
        return None


async def send_briefing_email() -> bool:
    """Generate briefing and send via email."""
    from app.services.email import send_email, is_configured

    if not is_configured():
        return False

    briefing = await generate_briefing()
    summary = briefing["summary"]
    date_str = datetime.now().strftime("%A, %B %d")

    # Convert markdown to simple HTML
    html = _markdown_to_email_html(summary, date_str)
    subject = f"PAM Daily Briefing — {date_str}"

    return await send_email(subject, html, body_text=summary)


async def build_checkin_summary(data: dict) -> str:
    """Build a short mid-day check-in focused on habits + calendar + one affirmation."""
    lines = []
    habits = data.get("habits", {})
    if habits.get("today_total", 0) > 0:
        lines.append(f"HABITS — {habits['today_done']}/{habits['today_total']} done today")
        for h in habits.get("habits", []):
            status = "done" if h.get("done") else "pending"
            lines.append(f"  {'✓' if h.get('done') else '○'} {h['text']}: {status}")

    cal = data.get("calendar", {})
    if cal.get("upcoming_count", 0) > 0:
        lines.append(f"\nUPCOMING — {cal['upcoming_count']} events")
        for e in cal.get("items", [])[:4]:
            lines.append(f"  - {e['summary']} ({e['start']})")

    accomp = data.get("accomplishments", {})
    if accomp.get("last_24h_count", 0) > 0:
        lines.append(f"\nRecent wins: {accomp['last_24h_count']} in last 24h")

    gratitude = data.get("gratitude", {})
    if gratitude.get("pillars"):
        lines.append(f"Gratitude pillars: {', '.join(gratitude['pillars'])}")

    data_text = "\n".join(lines)

    prompt = (
        "You are PAM. Generate a brief mid-day check-in (under 100 words). "
        "Cover: (1) which habits are done vs remaining today, (2) any upcoming events in the next few hours, "
        "(3) one concrete affirmation — reference a recent win or gratitude pillar. "
        "Keep it warm and short. Markdown formatting.\n\n"
        f"Current date/time: {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}\n\n"
        f"{data_text}"
    )

    from app.services.claude_cli import run_claude
    result = await run_claude(prompt, timeout=60)
    if result["ok"] and result["text"]:
        return result["text"]
    if result.get("error"):
        print(f"[PAM] Check-in Claude call failed: {result['error']}")

    return f"## Mid-Day Check-In\n\n{data_text}"


async def send_checkin_email() -> bool:
    """Generate check-in and send via email."""
    from app.services.email import send_email, is_configured

    if not is_configured():
        return False

    data = await build_briefing_data()
    summary = await build_checkin_summary(data)
    date_str = datetime.now().strftime("%A, %B %d")

    html = _markdown_to_email_html(summary, date_str)
    subject = f"PAM Check-In — {date_str}"

    return await send_email(subject, html, body_text=summary)


def _markdown_to_email_html(markdown: str, date_str: str) -> str:
    """Convert markdown briefing to inline-styled HTML for email."""
    import re

    # Simple markdown → HTML conversion for email
    lines = markdown.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
            continue
        if stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            text = stripped[3:]
            html_lines.append(f'<h2 style="color:#1e2433;font-size:16px;margin:16px 0 8px 0;font-family:sans-serif;">{text}</h2>')
        elif stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            text = stripped[4:]
            html_lines.append(f'<h3 style="color:#374151;font-size:14px;margin:12px 0 6px 0;font-family:sans-serif;">{text}</h3>')
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append('<ul style="margin:4px 0;padding-left:20px;">')
                in_list = True
            text = stripped[2:]
            # Bold
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            html_lines.append(f'<li style="font-size:14px;color:#374151;margin:2px 0;font-family:sans-serif;">{text}</li>')
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
            html_lines.append(f'<p style="font-size:14px;color:#374151;margin:6px 0;font-family:sans-serif;">{text}</p>')

    if in_list:
        html_lines.append("</ul>")

    body = "\n".join(html_lines)

    return f"""<!DOCTYPE html>
<html>
<body style="background:#f3f4f6;padding:24px;margin:0;">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
<div style="width:32px;height:32px;background:#3b82f6;border-radius:8px;display:flex;align-items:center;justify-content:center;color:white;font-weight:bold;font-family:sans-serif;">P</div>
<span style="font-weight:700;font-size:18px;color:#1e2433;font-family:sans-serif;">PAM — {date_str}</span>
</div>
{body}
<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">
<p style="font-size:11px;color:#9ca3af;font-family:sans-serif;">Sent by PAM</p>
</div>
</body>
</html>"""
