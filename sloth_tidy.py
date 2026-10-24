#!/usr/bin/env python3
"""sloth-tidy: a lazy, fully local file tidier.

Reads new files in a folder (e.g. Downloads), asks a local open-weight model
(Gemma via Ollama by default) which folder each one belongs in and what to
call it, then moves it. Nothing leaves your machine.

Extras:
  * finds identical files and asks which copy to keep (the other goes to
    Duplicates/, never deleted)
  * spots future dates (flights, exams, deadlines) and offers to create a
    calendar reminder (.ics file)
  * writes a short guide to _Sloth/GUIDE.md the first time it really runs

Safe by default: it only prints what it WOULD do until you pass --apply,
and every real run can be reverted with --undo.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import ollama
from pypdf import PdfReader

DEFAULT_MODEL = "gemma3:4b"
DEFAULT_CATEGORIES = ["Uni", "Receipts", "Travel", "Documents", "Work", "Other"]
LOG_NAME = ".sloth_tidy_log.json"
SLOTH_DIR = "_Sloth"
DUPLICATES_DIR = "Duplicates"
GUIDE_TEMPLATE = Path(__file__).with_name("guide_template.md")
FALLBACK_GUIDE = (
    "# sloth-tidy guide\n\n"
    "Dry run: python sloth_tidy.py <folder>\n"
    "Tidy for real: add --apply\n"
    "Undo the last run: add --undo\n"
)

# Obvious files are sorted by extension, so the model is only used when it adds value.
EXTENSION_RULES = {
    "Photos": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp"},
    "Installers": {".dmg", ".exe", ".msi", ".pkg", ".deb"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
}
TEXT_EXTS = {".txt", ".md", ".csv"}
# Files like these keep their own name: a sensible folder is enough, renaming them would be silly.
KEEP_NAME_EXTS = {
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php",
    ".html", ".css", ".json", ".xml", ".yml", ".yaml", ".sh", ".bat", ".ps1", ".sql", ".ipynb",
}
SKIP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download"}  # still downloading


# ---------- small helpers ----------

def slugify(text: str) -> str:
    """'My Flight Ticket (Rome)!' -> 'my-flight-ticket-rome'"""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def unique_path(dest: Path) -> Path:
    """Never overwrite: add -1, -2, ... if the target already exists."""
    if not dest.exists():
        return dest
    i = 1
    while True:
        candidate = dest.with_name(f"{dest.stem}-{i}{dest.suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def open_file(path: Path) -> None:
    """Open a file with the default app (used to hand a .ics file to your calendar)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        print(f"  Could not open it automatically. Open this file to add it to your calendar: {path}")


# ---------- reading and classifying ----------

def read_snippet(path: Path, limit: int = 1500) -> str:
    """First ~1500 characters of a PDF or text file (empty string if unreadable)."""
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            reader = PdfReader(str(path))
            return (reader.pages[0].extract_text() or "").strip()[:limit]
        if ext in TEXT_EXTS:
            return path.read_text(errors="ignore").strip()[:limit]
    except Exception:
        pass
    return ""


def rule_category(path: Path):
    """Folder chosen by file extension alone, or None if the model should decide."""
    ext = path.suffix.lower()
    for folder, exts in EXTENSION_RULES.items():
        if ext in exts:
            return folder
    return None


def parse_event(raw, today: date):
    """Validate an event suggested by the model. Returns a clean dict or None."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()[:100]
    date_text = str(raw.get("date") or "").strip()
    time_text = str(raw.get("time") or "").strip()
    if not title:
        return None
    try:
        day = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return None
    if day < today:
        return None  # past dates are never reminders
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time_text):
        time_text = ""
    return {"title": title, "date": day.isoformat(), "time": time_text}


def analyze(path: Path, categories: list, model: str) -> dict:
    """Return {"folder", "name", "event"} for one file."""
    rule = rule_category(path)
    if rule:
        return {"folder": rule, "name": None, "event": None}

    today = date.today()
    snippet = read_snippet(path)
    prompt = (
        "You sort files for a university student.\n"
        f"Today's date is {today.isoformat()}.\n"
        f"1) Choose exactly one folder from: {', '.join(categories)}.\n"
        "   Tickets for trips, transport or attractions belong in Travel. "
        "A proof of payment, receipt or invoice belongs in Receipts, even if it is for a trip.\n"
        "2) Suggest a short descriptive file name (lowercase words separated "
        "by hyphens, no extension).\n"
        "3) If the document clearly mentions a FUTURE date the student must attend or "
        "act on (flight, exam, appointment, deadline), describe it as an event. "
        "The event title must say what and where, using place or route names from the "
        "document (for example 'Flixbus Munich to Innsbruck' or 'Museum visit Amsterdam'). "
        "Receipts and invoices for past purchases are NOT events. Otherwise use null.\n"
        'Reply only with JSON: {"folder": "...", "name": "...", '
        '"event": {"title": "...", "date": "YYYY-MM-DD", "time": "HH:MM or empty"} or null}\n\n'
        f"File name: {path.name}\n"
        f"Content start:\n{snippet or '(no readable text)'}"
    )
    reply = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0},
    )
    try:
        data = json.loads(reply["message"]["content"])
    except (json.JSONDecodeError, KeyError, TypeError):
        data = None
    if not isinstance(data, dict):
        return {"folder": "Other", "name": None, "event": None, "read": bool(snippet)}

    folder = data.get("folder")
    if folder not in categories:
        folder = "Other"
    raw_name = data.get("name")
    name = (slugify(str(raw_name)) or None) if raw_name else None
    if path.suffix.lower() in KEEP_NAME_EXTS:
        name = None
    return {
        "folder": folder,
        "name": name,
        "event": parse_event(data.get("event"), today),
        "read": bool(snippet),
    }


def classify(path: Path, categories: list, model: str):
    """Return (folder, suggested_name_or_None) for one file."""
    result = analyze(path, categories, model)
    return result["folder"], result["name"]


# ---------- duplicates ----------

def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicate_groups(files: list) -> list:
    """Groups of byte-for-byte identical files, oldest first. Only same-size files are hashed."""
    by_size = {}
    for path in files:
        try:
            by_size.setdefault(path.stat().st_size, []).append(path)
        except OSError:
            continue
    groups = {}
    for size, same_size in by_size.items():
        if size == 0 or len(same_size) < 2:
            continue
        for path in same_size:
            try:
                groups.setdefault(file_hash(path), []).append(path)
            except OSError:
                continue
    return [
        sorted(group, key=lambda p: (p.stat().st_mtime, p.name))
        for group in groups.values()
        if len(group) > 1
    ]


def choose_duplicates(groups: list, interactive: bool) -> dict:
    """Return {duplicate_path: kept_path}. Asks which copy to keep when interactive."""
    duplicates = {}
    for group in groups:
        keep = group[0]
        if interactive:
            print("\nThese files are identical:")
            for i, path in enumerate(group, 1):
                print(f"  [{i}] {path.name}")
            answer = ask("Which one do you want to keep? Number, or 's' to keep all: ").strip().lower()
            if answer == "s":
                continue
            if answer.isdigit() and 1 <= int(answer) <= len(group):
                keep = group[int(answer) - 1]
            else:
                print("  Not understood, keeping the oldest one.")
        for path in group:
            if path != keep:
                duplicates[path] = keep
    return duplicates


# ---------- reminders ----------

def link_similar_events(items: list) -> list:
    """Flag reminder ideas that share a date and time (e.g. a ticket and its payment receipt).

    Nothing is merged or hidden: every idea is still offered, and you decide. Each idea just
    gets a `similar` list with the file names of the others that look like the same event.
    All-day events must also have the same title to count as similar.
    """
    groups = {}
    for item in items:
        event = item["event"]
        key = (event["date"], event["time"]) if event["time"] else (event["date"], slugify(event["title"]))
        groups.setdefault(key, []).append(item)
    for group in groups.values():
        for item in group:
            item["similar"] = [other["file"].name for other in group if other is not item]
    return items


def ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_ics(event: dict, source_name: str) -> str:
    """A calendar file with one event and an alert one day before."""
    day = datetime.strptime(event["date"], "%Y-%m-%d")
    if event["time"]:
        start = datetime.strptime(f"{event['date']} {event['time']}", "%Y-%m-%d %H:%M")
        start_line = f"DTSTART:{start:%Y%m%dT%H%M%S}"
        end_line = f"DTEND:{start + timedelta(hours=1):%Y%m%dT%H%M%S}"
    else:
        start_line = f"DTSTART;VALUE=DATE:{day:%Y%m%d}"
        end_line = f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//sloth-tidy//EN",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@sloth-tidy",
        f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        start_line,
        end_line,
        f"SUMMARY:{ics_escape(event['title'])}",
        f"DESCRIPTION:{ics_escape('From file: ' + source_name)}",
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{ics_escape(event['title'])}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def handle_reminders(folder: Path, events: list, apply: bool, interactive: bool) -> int:
    """Offer reminders for events found in documents. Returns how many were created or saved."""
    created = 0
    sloth = folder / SLOTH_DIR
    accepted = set()  # files whose reminder you already said yes to
    for item in events:
        event, target = item["event"], item["file"]
        when = event["date"] + (f" {event['time']}" if event["time"] else "")
        similar = item.get("similar", [])
        warning = f"  [same date and time as {', '.join(similar)}: maybe the same event]" if similar else ""
        print(f"  reminder idea: {event['title']} on {when} (from {target.name}){warning}")
        if not apply:
            continue  # dry run: only show
        if interactive:
            already = [name for name in similar if name in accepted]
            if already:
                question = (f"  You already added a reminder for the same date and time ({already[0]}). "
                            "Add another one anyway? [y/N] ")
            else:
                question = "  Create a calendar reminder for this? [y/N] "
            answer = ask(question).strip().lower()
            if answer not in ("y", "yes", "e", "evet"):
                continue
            accepted.add(target.name)
            out_dir = sloth / "Reminders"
            out_dir.mkdir(parents=True, exist_ok=True)
            ics = unique_path(out_dir / f"{slugify(event['title']) or 'reminder'}-{event['date']}.ics")
            ics.write_bytes(make_ics(event, target.name).encode("utf-8"))
            print(f"  Saved {ics.relative_to(folder)}. Opening it so you can add it to your calendar.")
            open_file(ics)
            created += 1
        else:
            # watch mode: nobody to ask, so keep a list to look at later
            sloth.mkdir(parents=True, exist_ok=True)
            with (sloth / "reminders.md").open("a", encoding="utf-8") as f:
                f.write(f"- {when}: {event['title']} (file: {target.name})\n")
            created += 1
    return created


# ---------- first-run guide ----------

def ensure_guide(folder: Path) -> None:
    guide = folder / SLOTH_DIR / "GUIDE.md"
    if guide.exists():
        return
    guide.parent.mkdir(parents=True, exist_ok=True)
    text = GUIDE_TEMPLATE.read_text(encoding="utf-8") if GUIDE_TEMPLATE.exists() else FALLBACK_GUIDE
    guide.write_text(text, encoding="utf-8")
    print(f"\nFirst run: I put a short guide in {guide.relative_to(folder)}")


# ---------- main work ----------

def write_log(folder: Path, moves: list) -> None:
    log_path = folder / LOG_NAME
    runs = json.loads(log_path.read_text()) if log_path.exists() else []
    runs.append({"time": datetime.now().isoformat(timespec="seconds"), "moves": moves})
    log_path.write_text(json.dumps(runs, indent=2))


def tidy(folder: Path, model: str, categories: list, apply: bool,
         min_age: int = 60, interactive: bool = False) -> dict:
    """Sort the files directly inside `folder`. Returns counts of what was (or would be) moved."""
    moves, events, now = [], [], time.time()
    stats = {"files": 0, "by_rule": 0, "by_model": 0, "duplicates": 0, "reminders": 0, "no_text": 0}

    candidates = [
        p for p in sorted(folder.iterdir())
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() not in SKIP_SUFFIXES
        and now - p.stat().st_mtime >= min_age  # newer files are probably still being written
    ]
    duplicates = choose_duplicates(find_duplicate_groups(candidates), interactive)

    for path in candidates:
        if path in duplicates:
            target = unique_path(folder / DUPLICATES_DIR / path.name)
            note = f"  (identical to {duplicates[path].name})"
            stats["duplicates"] += 1
        else:
            stats["by_rule" if rule_category(path) else "by_model"] += 1
            result = analyze(path, categories, model)
            target = unique_path(folder / result["folder"] / f"{result['name'] or path.stem}{path.suffix.lower()}")
            note = ""
            if not result.get("read", True):
                note = "  [no readable text, judged by file name only]"
                stats["no_text"] += 1
            if result["event"]:
                events.append({"file": target, "event": result["event"]})
        print(f"{path.name}  ->  {target.relative_to(folder)}{note}")
        stats["files"] += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            moves.append({"from": str(path), "to": str(target)})

    if apply and moves:
        write_log(folder, moves)
    if apply:
        ensure_guide(folder)
    if events:
        print()
        stats["reminders"] = handle_reminders(folder, link_similar_events(events), apply, interactive)
    return stats


def undo(folder: Path) -> None:
    """Revert the most recent real run."""
    log_path = folder / LOG_NAME
    runs = json.loads(log_path.read_text()) if log_path.exists() else []
    if not runs:
        print("Nothing to undo.")
        return
    run = runs.pop()
    restored = skipped = 0
    for move in reversed(run["moves"]):
        src, dst = Path(move["to"]), Path(move["from"])
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            print(f"restored {dst.name}")
            restored += 1
            try:
                src.parent.rmdir()  # remove the category folder if it is now empty
            except OSError:
                pass
        else:
            print(f"skipped {src.name} (not at its new location, or the original name is taken)")
            skipped += 1
    log_path.write_text(json.dumps(runs, indent=2))
    print(f"\nUndo: restored {restored} file(s), skipped {skipped}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lazy local file tidier (Ollama + open-weight model).")
    parser.add_argument("folder", type=Path, help="folder to tidy, e.g. ~/Downloads")
    parser.add_argument("--apply", action="store_true", help="really move files (default: dry run)")
    parser.add_argument("--undo", action="store_true", help="revert the last real run")
    parser.add_argument("--watch", type=int, metavar="SECONDS", help="keep running and tidy every N seconds (implies --apply)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    parser.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES), help="comma-separated folder names")
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        print(f"Not a folder: {folder}")
        return 1
    if args.undo:
        undo(folder)
        return 0

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    if "Other" not in categories:
        categories.append("Other")

    try:
        if args.watch:
            print(f"Watching {folder} every {args.watch}s. Ctrl+C to stop.")
            while True:
                tidy(folder, args.model, categories, apply=True, interactive=False)
                time.sleep(args.watch)
        else:
            interactive = args.apply and sys.stdin.isatty()
            started = time.time()
            stats = tidy(folder, args.model, categories, apply=args.apply, interactive=interactive)
            took = time.time() - started
            verb = "Moved" if args.apply else "Dry run: would move"
            extra = f", {stats['duplicates']} duplicate(s)" if stats["duplicates"] else ""
            if stats["no_text"]:
                extra += f", {stats['no_text']} without readable text"
            print(
                f"\n{verb} {stats['files']} file(s) in {took:.1f}s "
                f"({stats['by_rule']} by extension rules, {stats['by_model']} by the model{extra})."
            )
            if not args.apply:
                print("Re-run with --apply to do it.")
    except ConnectionError:
        print("Can't reach Ollama. Is it running? Start the Ollama app, or run: ollama serve")
        return 1
    except ollama.ResponseError as err:
        print(f"Ollama error: {err}\nIf the model is missing, run: ollama pull {args.model}")
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
