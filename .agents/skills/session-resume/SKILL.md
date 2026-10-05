---
name: session-resume
description: >-
  Inspects and recovers project progress, state, and context from previous sessions.
  Use when starting or resuming a session, when asked "where did we leave off?",
  "à quel niveau on s'est arrêté", or to track and persist session checkpoints.
---

# Session Resume & Progress Tracker

This skill provides standard procedures for identifying the exact progress level of a project across sessions, restoring full context, and saving progress checkpoints.

## When to Use
- At the start of a session or when the user asks where work stopped previously.
- When resuming work after context resets, system reboots, or handovers.
- Before ending a session to record a checkpoint of what was accomplished and what remains.

---

## 1. Resume Procedure (Step-by-Step)

When instructed to find where work stopped:

### Step 1: Inspect Git & Working Tree
Run:
```bash
git status --short
git log -n 5 --oneline --decorate
git branch -vv
```
Analyze:
- Any uncommitted or untracked changes.
- The latest commit message, hash, and author date.
- Active branch and synchronization with upstream.

### Step 2: Read Project Checkpoint & Mindmap
1. Check if `.session_checkpoint.json` exists in project root.
2. Check `docs/MINDMAP_SystemOrion.md` and `docs/CDC_SystemOrion_v1_3.md` for current phase and status markers (✅, ⚠️, 🚧).
3. If checkpoint exists, parse:
   - `last_session_date`
   - `completed_features`
   - `current_task`
   - `blocked_or_failing_tests`
   - `next_steps`

### Step 3: Verify Test Suite Baseline
Run test suite to verify current health:
```bash
.venv/bin/python -m pytest tests/ -q
```
Note any failing tests, regressions, or skipped suites.

### Step 4: Synthesize & Report to User
Provide a brief, high-clarity status report:
- **Dernier niveau validé** (dernière fonctionnalité terminée)
- **Tâche en cours** (ce qui était en train d'être codé/testé)
- **État des tests** (X/Y tests passés, régressions éventuelles)
- **Prochaines actions immédiates recommandées**

---

## 2. Checkpoint Persistence Procedure

When ending a phase, achieving a milestone, or when requested:
1. Update `docs/MINDMAP_SystemOrion.md` with new markers.
2. Update `.session_checkpoint.json` at repository root with:
```json
{
  "project": "System Orion",
  "version": "0.1.0",
  "updated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "last_milestone": "Description du jalon terminé",
  "completed_items": ["item 1", "item 2"],
  "in_progress": "Description de la tâche courante",
  "failing_tests": [],
  "next_priorities": ["P1", "P2"]
}
```
3. Commit clean atomic changes with informative message.
