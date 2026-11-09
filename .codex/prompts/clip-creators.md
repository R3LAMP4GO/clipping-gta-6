---
description: List, add or remove the creators the GTA 6 clipper watches
argument-hint: [add @handle | remove name | list]
---

Manage the creators list for the GTA 6 clipper (run from the clipping-gta-6 project root).

Input: $ARGUMENTS

- If it says what to do (e.g. "add @KaiCenat @xQcOW", "remove VanossGaming"), run `python3 -m clipper creators add <refs…>` or `python3 -m clipper creators remove <refs…>`. Refs can be @handles, handles or channel URLs; each add is checked against YouTube.
- Otherwise run `python3 -m clipper creators list`, show the list as a table, and ask: "Add creators", "Remove creators" or "Done". Ask with multiple-choice questions: in Claude Code use the AskUserQuestion tool; in Codex use request_user_input if available (Plan mode), otherwise list numbered options and wait for the reply. For add, ask for handles or URLs as free text; for remove, offer the current creators as a multi-select.
- After any change, show the updated list. Remind the user that every upload is still checked for GTA 6 (title, description or tags), so adding a variety creator only brings in their GTA 6 videos.
