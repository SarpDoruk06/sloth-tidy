#!/usr/bin/env python3
"""Show what sloth-tidy can actually READ from a file (nothing is moved or changed).

    python peek.py "Adult - 1.pdf"

If it prints "No readable text", the file is probably a scan or a picture inside a PDF.
The model then only sees the file name, so its choice is a guess.
"""
import sys
from pathlib import Path

from sloth_tidy import read_snippet


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: python peek.py "path/to/file.pdf"')
        return 1
    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        print(f"Not a file: {path}")
        return 1
    text = read_snippet(path)
    if not text:
        print("No readable text. The model would judge this file by its name only.")
        return 0
    print(f"Readable text found ({len(text)} characters). The model sees this:\n")
    print(text[:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
