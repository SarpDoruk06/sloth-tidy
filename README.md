# sloth-tidy 🦥

A lazy, fully local file tidier. Point it at a messy folder (like Downloads) and a
local open-weight model (Gemma, via Ollama) decides which folder each file belongs
in and gives it a readable name. No cloud, no API key, no account.

Built for the DEV / Hacktoberfest Open-Source AI Challenge, Week 3: "Slow and Steady".

## Why open-source AI matters here

- **Privacy:** your documents (receipts, uni PDFs, tickets) never leave your laptop.
- **Free and offline:** after the one-time model download it costs nothing and needs no internet.
- **Swappable:** try another model with `--model` (for example `qwen2.5:3b`) if the first sorts badly.

## How it works

1. Obvious files (images, installers, archives) are sorted by extension, with no model call.
2. For everything else it reads the first page of a PDF or text file and asks the local model for JSON: `{"folder": ..., "name": ...}`.
3. The answer is validated (unknown folders become `Other`, names are cleaned up).
4. Files are moved without ever overwriting anything. Every real run is logged so `--undo` can revert it.

## Setup

1. Install Ollama from https://ollama.com
2. Download a model: `ollama pull gemma3:4b`
3. Install the Python libraries: `pip install -r requirements.txt`

## Usage

```bash
# Dry run (default): only prints what it would do
python sloth_tidy.py ~/Downloads

# Actually move the files
python sloth_tidy.py ~/Downloads --apply

# Changed your mind? Revert the last run
python sloth_tidy.py ~/Downloads --undo

# Really lazy: keep tidying every 10 minutes
python sloth_tidy.py ~/Downloads --watch 600

# Your own folders, or another model
python sloth_tidy.py ~/Downloads --categories "Uni,Receipts,Travel,Sport" --model qwen2.5:3b
```

Try it on a copy of a messy folder first.

## Tests

```bash
pip install pytest
pytest
```

## Honest limitations

- Small models sometimes pick the wrong folder. That is why dry run is the default and `--undo` exists.
- Only the top level of the folder is tidied, and only PDFs and plain text are read. Other files are judged by name.

## Credits

Uses [Ollama](https://ollama.com), [Gemma](https://ai.google.dev/gemma) and [pypdf](https://pypdf.readthedocs.io).
Started and built during the challenge window (19 to 25 October 2026).
