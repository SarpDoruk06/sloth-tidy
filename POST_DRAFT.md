---
title: sloth-tidy: a lazy local file tidier powered by Gemma
published: false
tags: devchallenge, hf26challenge
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

<!-- Write this in your own voice. Start with the real problem: YOUR Downloads folder. How many files? What was in it? -->
sloth-tidy is a small Python tool that cleans a messy folder for you. A local open-weight model reads each new file, decides which folder it belongs in (Uni, Receipts, Travel...), gives it a readable name, and moves it. It runs entirely on my laptop.

[Describe who gets to be lazier: e.g. students whose Downloads folder is full of lecture PDFs, tickets and receipts.]

## Demo

<!-- Add a short screen recording or before/after screenshots of YOUR real (copied) folder. -->
[Video or screenshots here]

## Code

{% embed https://github.com/YOUR-USERNAME/sloth-tidy %}

## How I Built It

- **Model:** Gemma (`gemma3:4b`) running locally through Ollama.
- **Flow:** obvious files (images, installers, archives) are sorted by extension. For documents, the first page of text is sent to the model, which replies with JSON (`folder` and `name`). The reply is validated before anything moves.
- **Safety:** dry run by default, nothing is ever overwritten, and `--undo` reverts the last run.
- **Tests and CI:** a few pytest tests run on every push with GitHub Actions.

[Add one real thing that went wrong while building and how you fixed it. Judges like honesty.]

## Why Does Open Innovation Matter?

<!-- Your strongest section. Keep it concrete and personal. -->
- **My files stay mine.** Receipts, uni documents and tickets never leave my laptop. With a closed API I would be uploading personal documents to a server I do not control.
- **It works offline and costs nothing** after the one-time model download.
- **I could swap models.** [Say what you actually tried, e.g. Gemma vs Qwen, and what you saw.]
- [One honest limit: small models sometimes choose the wrong folder, so dry run and undo are built in.]

## The Lazy Payoff

[Only add real numbers. Example: "I ran it on a copy of my Downloads folder: X files sorted in Y minutes, Z were wrong." Delete this section if you do not have real results.]

## Prize Categories

<!-- List only the categories you genuinely used. -->
- **Best Use of Gemma:** the whole project runs on Gemma locally through Ollama.
- [Add Best Use of GitHub Copilot, Best Use of a .tech Domain or Best Use of ElevenLabs ONLY if you really used them.]
