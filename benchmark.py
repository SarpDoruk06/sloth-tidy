#!/usr/bin/env python3
"""Measure how accurate the local model is at sorting YOUR files. Nothing is moved.

Step 1: make a template of the files in a folder:
    python benchmark.py ~/Desktop/test-tidy --template

Step 2: open expected.csv and fill the second column with the folder each
file SHOULD go to (for example Uni, Receipts, Travel, Photos, Other).

Step 3: run the benchmark, optionally with several models to compare them:
    python benchmark.py ~/Desktop/test-tidy --model gemma3:4b --model qwen2.5:3b
"""
import argparse
import csv
import sys
import time
from pathlib import Path

import ollama

from sloth_tidy import DEFAULT_CATEGORIES, DEFAULT_MODEL, classify


def make_template(folder: Path, csv_path: Path) -> None:
    files = sorted(p.name for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "expected_folder"])
        for name in files:
            writer.writerow([name, ""])
    print(f"Wrote {csv_path} with {len(files)} file(s). Fill the second column, then run again without --template.")


def load_expected(csv_path: Path) -> dict:
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return {r[0].strip(): r[1].strip() for r in rows[1:] if len(r) >= 2 and r[1].strip()}


def run_model(folder: Path, expected: dict, model: str, categories: list) -> None:
    print(f"\n=== {model} ===")
    correct, total, started = 0, 0, time.time()
    for name, want in expected.items():
        path = folder / name
        if not path.is_file():
            print(f"MISSING  {name} (not in the folder, skipped)")
            continue
        got, _ = classify(path, categories, model)
        ok = got.lower() == want.lower()
        correct += ok
        total += 1
        print(f"{'OK    ' if ok else 'WRONG '}  {name}: expected {want}, got {got}")
    took = time.time() - started
    if total:
        print(f"\n{model}: {correct}/{total} correct ({100 * correct / total:.0f}%) in {took:.1f}s")
    else:
        print("No files were checked.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Accuracy check for sloth-tidy (nothing is moved).")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--csv", type=Path, default=None, help="expected folders file (default: <folder>/expected.csv)")
    parser.add_argument("--template", action="store_true", help="create the expected.csv template and exit")
    parser.add_argument("--model", action="append", help=f"model to test, can be repeated (default {DEFAULT_MODEL})")
    parser.add_argument("--categories", default=",".join(DEFAULT_CATEGORIES))
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    csv_path = args.csv or (folder / "expected.csv")
    if args.template:
        make_template(folder, csv_path)
        return 0
    if not csv_path.exists():
        print(f"No {csv_path}. Run with --template first.")
        return 1

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    if "Other" not in categories:
        categories.append("Other")
    expected = load_expected(csv_path)
    try:
        for model in args.model or [DEFAULT_MODEL]:
            run_model(folder, expected, model, categories)
    except ConnectionError:
        print("Can't reach Ollama. Is it running?")
        return 1
    except ollama.ResponseError as err:
        print(f"Ollama error: {err}\nIf a model is missing, run: ollama pull <model>")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
