#!/usr/bin/env python3
"""sloth-tidy: a lazy, fully local file tidier.

Reads new files in a folder (e.g. Downloads), asks a local open-weight model
(Gemma via Ollama by default) which folder each one belongs in and what to
call it, then moves it. Nothing leaves your machine.

Safe by default: it only prints what it WOULD do until you pass --apply,
and every real run can be reverted with --undo.
"""
import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import ollama
from pypdf import PdfReader

DEFAULT_MODEL = "gemma3:4b"
DEFAULT_CATEGORIES = ["Uni", "Receipts", "Travel", "Documents", "Work", "Other"]
LOG_NAME = ".sloth_tidy_log.json"

# Obvious files are sorted by extension, so the model is only used when it adds value.
EXTENSION_RULES = {
    "Photos": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp"},
    "Installers": {".dmg", ".exe", ".msi", ".pkg", ".deb"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
}
TEXT_EXTS = {".txt", ".md", ".csv"}
SKIP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download"}  # still downloading


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


def read_snippet(path: Path, limit: int = 1500) -> str:
    """First ~1500 characters of a PDF or text file (empty string if unreadable)."""
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            reader = PdfReader(str(path))
            return (reader.pages[0].extract_text() or "")[:limit]
        if ext in TEXT_EXTS:
            return path.read_text(errors="ignore")[:limit]
    except Exception:
        pass
    return ""


def classify(path: Path, categories: list, model: str):
    """Return (folder, suggested_name_or_None) for one file."""
    ext = path.suffix.lower()
    for folder, exts in EXTENSION_RULES.items():
        if ext in exts:
            return folder, None

    snippet = read_snippet(path)
    prompt = (
        "You sort files for a university student.\n"
        f"Choose exactly one folder from: {', '.join(categories)}.\n"
        "Also suggest a short descriptive file name (lowercase words separated "
        "by hyphens, no extension).\n"
        'Reply only with JSON: {"folder": "...", "name": "..."}\n\n'
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
        return "Other", None

    folder = data.get("folder") if isinstance(data, dict) else None
    if folder not in categories:
        folder = "Other"
    name = slugify(str(data.get("name", ""))) if isinstance(data, dict) else ""
    return folder, (name or None)


def write_log(folder: Path, moves: list) -> None:
    log_path = folder / LOG_NAME
    runs = json.loads(log_path.read_text()) if log_path.exists() else []
    runs.append({"time": datetime.now().isoformat(timespec="seconds"), "moves": moves})
    log_path.write_text(json.dumps(runs, indent=2))


def tidy(folder: Path, model: str, categories: list, apply: bool, min_age: int = 60) -> int:
    """Sort the files directly inside `folder`. Returns how many files were (or would be) moved."""
    moves, count, now = [], 0, time.time()
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if now - path.stat().st_mtime < min_age:
            continue  # modified in the last minute, probably still being written

        category, new_name = classify(path, categories, model)
        target = unique_path(folder / category / f"{new_name or path.stem}{path.suffix.lower()}")
        print(f"{path.name}  ->  {target.relative_to(folder)}")
        count += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
            moves.append({"from": str(path), "to": str(target)})

    if apply and moves:
        write_log(folder, moves)
    return count


def undo(folder: Path) -> None:
    """Revert the most recent real run."""
    log_path = folder / LOG_NAME
    runs = json.loads(log_path.read_text()) if log_path.exists() else []
    if not runs:
        print("Nothing to undo.")
        return
    run = runs.pop()
    for move in reversed(run["moves"]):
        src, dst = Path(move["to"]), Path(move["from"])
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            print(f"restored {dst.name}")
        else:
            print(f"skipped {src.name} (moved or renamed since)")
    log_path.write_text(json.dumps(runs, indent=2))


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
                tidy(folder, args.model, categories, apply=True)
                time.sleep(args.watch)
        else:
            count = tidy(folder, args.model, categories, apply=args.apply)
            if not args.apply:
                print(f"\nDry run: {count} file(s) would move. Re-run with --apply to do it.")
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
