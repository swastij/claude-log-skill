---
name: log
description: Log this session's learnings (decisions, insights, questions, quiz) for a task to the personal Notion "Engineering learnings" databases. Use when the user says /log, "log this", "save learnings", or when a PR is opened or a task reaches Done and the user wants the insight captured.
---

# /log — capture learnings to Notion

Personal knowledge base, not team-facing. Script: `~/.claude/scripts/notion-log.py`.
Entry files go in the scratchpad dir (or a temp dir), named `log-<task_id>.json`.
Setup and the Notion template: https://github.com/swastij/claude-log-skill

## Steps

1. **Identify the task.** Task ID (ClickUp `CU-...` by default; any tracker id works, it is only used as the upsert key) from the branch name, PR body or the user. If none exists, ask. Collect PR URLs for every repo touched.

2. **Draft the entry** from the session. Write it as JSON (shape in the script docstring) and SHOW it to the user as a short readable summary, not raw JSON. Rules:
   - `surprised_me` / `how_it_works` / `would_bite_again`: one paragraph each, mechanism not diff. Leave empty if the task was trivial; never pad.
   - `decisions`: every product/architecture/security choice made this session, each with **why** and **alternatives rejected**. Workarounds and deferred items are decisions too (`kind: workaround|deferred`).
   - `questions` with `source: "I asked"`: notable questions the user asked that changed the outcome. Rate 1–5 by how much it mattered.
   - `questions` with `source: "should have asked"`: questions that, had they been asked earlier, would have saved rework or caught a bug. Rate 1–5 by cost of not asking. Be honest; this is the most valuable list.
   - `spawned_from`: set when this task was opened because of another logged task.
   - `risk`: high for auth, payments, migrations, infra, data deletion.

3. **If status is Done** (merged / shipped): add 3–5 `source: "quiz"` questions with `correct_answer` filled and `my_answer` empty. Make them about mechanism and failure modes ("what happens if X", "why not Y"), not trivia. Set `shipped_on` to today.

4. **Wait for the user's edits.** Apply them to the JSON. Do not send before they confirm.

5. **Send:** `python3 -I ~/.claude/scripts/notion-log.py <file>`. Report the script's output lines verbatim. Re-running is safe: task is upserted by task ID, rows with an existing title are skipped.

## Don'ts
- Don't put anything secret (tokens, customer data) in an entry.
- Don't set `status` unless the user confirms it; the task tracker is the source of truth.
- Don't invent decisions the session didn't make.
