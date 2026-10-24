# sloth-tidy guide

This file was created automatically the first time sloth-tidy tidied this folder.
You can edit or delete it. It is copied from `guide_template.md` in the project.

## What sloth-tidy does

It looks at the files in this folder and moves each one into a folder that fits
(for example Uni, Receipts, Travel). A small AI model that runs on your own
computer reads the first page of documents to decide. Nothing is uploaded.

## Folders it creates

- `Uni`, `Receipts`, `Travel`, `Documents`, `Work`, `Other`: sorted documents.
- `Photos`, `Installers`, `Archives`: sorted by file type, without using the AI.
- `Duplicates`: extra copies of identical files. Nothing is ever deleted.
- `_Sloth`: this guide, your reminders and a list of reminder ideas.

## Commands

Run these from the sloth-tidy project folder. Replace `FOLDER` with the folder you want to tidy.

| I want to... | Command |
|---|---|
| See what would happen, without moving anything | `py sloth_tidy.py FOLDER` |
| Tidy the folder for real | `py sloth_tidy.py FOLDER --apply` |
| Undo the last tidy | `py sloth_tidy.py FOLDER --undo` |
| Keep tidying automatically every 10 minutes | `py sloth_tidy.py FOLDER --watch 600` |
| Use my own folder names | `py sloth_tidy.py FOLDER --categories "Uni,Receipts,Sport"` |
| Use a different AI model | `py sloth_tidy.py FOLDER --model qwen2.5:3b` |

Always start with the dry run. Files changed in the last minute are skipped
because they may still be downloading.

## Reminders

If a document mentions a future date (a flight, an exam, a deadline), sloth-tidy
tells you and asks: "Create a calendar reminder for this? [y/N]".

- Answer `y` to get a calendar file in `_Sloth/Reminders`. It opens automatically,
  and you add it to your calendar with one click. It includes an alert one day before.
- Small AI models can misread dates, so always check the date before you save it.
- In watch mode there is nobody to ask, so ideas are written to `_Sloth/reminders.md`.

## Duplicates

If two files are exactly the same, sloth-tidy asks which one to keep. The other
one is moved to `Duplicates`. In watch mode the oldest copy is kept automatically.
Use `--undo` to bring a file back.

## Checking how accurate the AI is

Use `benchmark.py` in the project folder. It never moves files:

1. `py benchmark.py FOLDER --template` creates `expected.csv`.
2. Fill in the correct folder for each file.
3. `py benchmark.py FOLDER` shows how many it got right.
