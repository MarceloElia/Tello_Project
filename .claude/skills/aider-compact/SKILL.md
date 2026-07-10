---
name: aider-compact
description: Compact the last N Aider sessions from .aider.chat.history.md into .aider.memory.md, then wire it into the local .aider.conf.yml so every new session reads it automatically. Run with /aider-compact [N] (default N=5).
allowed-tools: Read, Write, Bash(test *), Bash(ls *), Bash(date *)
---

Compact recent Aider session history into a persistent memory file for this project.

## Step 1 — Parse the argument

The user may have typed `/aider-compact` (use N=5) or `/aider-compact 3` (use N=3).
Extract N from the args if provided, otherwise default to 5.

## Step 2 — Check history exists

Check if `.aider.chat.history.md` exists in the current directory.
If it does not exist, tell the user: "No .aider.chat.history.md found in this directory.
Run aider at least once first, then compact." Stop here.

## Step 3 — Read the history file

Read `.aider.chat.history.md` in full.

Sessions are separated by lines starting with `# aider chat started at`.
Split the file into individual sessions on those headers.
Take the **last N sessions** (most recent). If fewer than N sessions exist, take all of them.

## Step 4 — Summarise into memory

For each of the N sessions, extract:
- Which files were added or edited (lines starting with `>` that reference file paths)
- What the user asked for (lines starting with `####`)
- Whether the change was applied or rejected (look for "Applied edit" / "Rejected" /
  "I'll leave that" patterns in the assistant turns)

Then write a **compact summary** — not a transcript, a distillation:

```
# Aider Session Memory
*Compacted [date] — last [N] sessions from .aider.chat.history.md*
*Reload anytime: /aider-compact*

## Recent changes (newest first)
- `path/to/file.py`: [one-line description of what changed] — [date]
- ...

## Patterns established
- [any recurring approach or decision that emerged, e.g. "always use cm not m for distances"]
- [conventions confirmed, e.g. "German comments are kept in German"]

## Files most often touched
- `path/to/file.py` ([N] times)
- ...

## Tasks that were attempted but failed or reverted
- [description] in `file.py` — [why it failed if visible]
```

Keep each bullet to one line. The whole file should stay under 80 lines so Aider
can load it cheaply on every session start.

## Step 5 — Write .aider.memory.md

Write the summary to `.aider.memory.md` in the current directory.
If the file already exists, **replace it entirely** (this is a compact, not an append).

## Step 6 — Wire into local .aider.conf.yml

Check if `.aider.conf.yml` exists in the current directory (not the parent ~/Projects/ one).

- **If it does not exist**: create it with:
  ```yaml
  read:
    - .aider.memory.md
  ```

- **If it exists**: read it, then check if `.aider.memory.md` is already in the `read` list.
  If not, add it. Preserve all other existing keys exactly.

This means `aider` (which inherits the global model config from ~/Projects/.aider.conf.yml)
will now also read `.aider.memory.md` automatically on every session start in this project.

## Step 7 — Report

Print a short summary:
- How many sessions were compacted
- How many lines .aider.memory.md contains
- Confirm .aider.conf.yml is updated
- Tell the user: "Next time you run `aider` in this folder, it will load .aider.memory.md automatically."
