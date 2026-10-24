# sloth-tidy 🦥

A lazy, fully local file tidier. Point it at a messy folder (like Downloads) and a
local open-weight model (Gemma, via Ollama) decides which folder each file belongs
in and gives it a readable name. No cloud, no API key, no account.

Built for the DEV / Hacktoberfest Open-Source AI Challenge, Week 3: "Slow and Steady".

## What it does

- **Sorts files** into folders such as Uni, Receipts, Travel. Photos, installers and
  archives are sorted by file type without using the model.
- **Offers calendar reminders.** If a document mentions a future date (a flight, an exam,
  a deadline), it asks "Create a calendar reminder? [y/N]". Say yes and it makes a `.ics`
  file with an alert one day before and opens it in your calendar app.
- **Finds duplicates.** If two files are byte-for-byte identical it asks which to keep.
  The other goes to `Duplicates/`. Nothing is ever deleted.
- **Explains itself.** The first time it really runs, it writes `_Sloth/GUIDE.md` into the
  folder, with every command in plain language. Edit `guide_template.md` to change the text.
- **Is safe.** Dry run by default, never overwrites a file, and `--undo` reverts the last run.

## Why open-source AI matters here

- **Privacy:** your documents (receipts, uni PDFs, tickets) never leave your laptop.
- **Free and offline:** after the one-time model download it costs nothing and needs no internet.
- **Swappable:** try another model with `--model` (for example `qwen2.5:3b`) if the first sorts badly.

## How it works

1. Obvious files (images, installers, archives) are sorted by extension, with no model call.
2. For everything else it reads the first page of a PDF or text file and asks the local model for JSON:
   a folder, a short file name, and an event if the document mentions a future date.
3. The answer is validated: unknown folders become `Other`, names are cleaned up, and
   events must have a real date in the future.
4. Identical files are found by comparing SHA-256 hashes (only files of the same size are hashed).
5. Files are moved without ever overwriting anything. Every real run is logged so `--undo` can revert it.

## Setup

1. Install Ollama from https://ollama.com
2. Download a model: `ollama pull gemma3:4b`
3. Install the Python libraries: `py -m pip install -r requirements.txt` (on Mac/Linux: `pip install -r requirements.txt`)

## Usage

```bash
# Dry run (default): only prints what it would do
python sloth_tidy.py ~/Downloads

# Actually move the files (asks about duplicates and reminders)
python sloth_tidy.py ~/Downloads --apply

# Changed your mind? Revert the last run
python sloth_tidy.py ~/Downloads --undo

# Really lazy: keep tidying every 10 minutes
python sloth_tidy.py ~/Downloads --watch 600

# Your own folders, or another model
python sloth_tidy.py ~/Downloads --categories "Uni,Receipts,Travel,Sport" --model qwen2.5:3b
```

On Windows use `py` instead of `python`. Try it on a copy of a messy folder first.

In `--watch` mode nobody is there to answer questions, so the oldest copy of a duplicate is
kept automatically, and reminder ideas are written to `_Sloth/reminders.md` instead.

## How accurate is it?

`benchmark.py` measures it on your own files and never moves anything:

```bash
python benchmark.py ~/Desktop/test-tidy --template        # creates expected.csv
# fill in the correct folder for each file, then:
python benchmark.py ~/Desktop/test-tidy --model gemma3:4b --model qwen2.5:3b
```

## Tests

```bash
pip install pytest
pytest
```

## Honest limitations

- Small models sometimes pick the wrong folder or misread a date. That is why dry run is the
  default, reminders need your "yes", and `--undo` exists. Always check a date before saving it.
- Only the top level of the folder is tidied, and only PDFs and plain text are read.
  Scanned PDFs (photos of paper) have no text to read, so those are judged by file name only.
  They are marked `[no readable text...]` in the output, and `python peek.py file.pdf` shows
  exactly what the model can read from a file. There is no OCR.
- Code files (.py, .js, ...) are sorted but keep their own name.
- If a ticket and its payment receipt mention the same date and time, you are asked about both,
  with a warning that they may be the same event. Nothing is hidden or merged for you.

## Credits

Uses [Ollama](https://ollama.com), [Gemma](https://ai.google.dev/gemma) and [pypdf](https://pypdf.readthedocs.io).
Started and built during the challenge window (19 to 25 October 2026).
