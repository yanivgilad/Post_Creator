# Stage 4 — Keyword management UI + LLM recommendations

**Goal:** Replace the static `sources.json` keyword list with a user-managed list in SQLite. Position in the list becomes a weight that influences ranking. Add a screen to view, reorder, edit, delete, and add keywords, plus an LLM-driven "suggest more" action.

**Branch off:** main (after the Stage 3 close commit).

**Why now:** today every keyword is treated equally, and the list is config in `sources.json`. Yaniv sees too many irrelevant items because the keyword list does not reflect what he actually cares about right now. Moving control into the UI and giving each keyword a weight derived from its position lets him sharpen relevance without touching code.

**Provider context:** same as Stage 3 — Azure OpenAI, default deployment `gpt-4o`. The new LLM-based suggestion endpoint reuses `LLMUsageTracker` from the Stage 3 cost-tracking commit, so its cost is captured in the cumulative totals.

**Permissions note:** reads/searches auto-run; edits, deletes, and git commit/push still prompt. Same as Stage 3.

---

## Feature 1 — DB-backed keywords with position weights

- New SQLite table `keywords` with columns: `id`, `text`, `position` (0 = top, most important), `created_at`. Weight is computed from position on read; not stored explicitly so reordering is just an `UPDATE position` and never has to re-compute weights.
- On startup (or `init-db`), if the table is empty, seed from `sources.json`'s current `keywords` list in the same order. Seeding is **one-shot** — once the user edits, re-running `init-db` does NOT overwrite.
- Weight formula: linear from `1.0` (position 0) to `0.1` (last position). With `N` keywords: `weight(i) = 1.0 - 0.9 * (i / max(N-1, 1))`. Top stays `1.0`, bottom stays `0.1`. Single-keyword case = `1.0`.
- `Settings.keywords` becomes legacy-only (still loaded from `sources.json` as the seed source). Runtime reads the live list from `SQLiteStore.list_keywords()`.
- `matches_keywords` in `sources/base.py` becomes `match_keyword_weight(text, keywords_with_weight)` returning the max weight of any matching keyword (`0.0` if none match).
- `ranking/scorer.py` multiplies the existing `rank_score` by `(1.0 + matched_weight)`. A top-keyword hit roughly doubles the score; a bottom-keyword hit barely lifts it. Items with no match score `1.0x` (no penalty).

## Feature 2 — CRUD + reorder UI at `/keywords`

- New page `/keywords` in the dashboard, linked from the top nav.
- Shows the ordered list with: drag handle, inline-editable text, computed weight (read-only, derived from position), delete button per row.
- "+ Add keyword" form at the bottom (text input + add button → inserts at bottom of list).
- Drag-and-drop reorder using HTML5 native drag events (no JS library). Server persists the new order on drop via a single batched call.
- All ops via dedicated endpoints under `/api/keywords`:
  - `GET /api/keywords` → ordered list with computed weights.
  - `POST /api/keywords` body `{text}` → create at bottom.
  - `PATCH /api/keywords/{id}` body `{text}` → rename.
  - `DELETE /api/keywords/{id}` → remove and compact positions.
  - `PUT /api/keywords/order` body `{ids: [int]}` → reorder atomically.

## Feature 3 — LLM-driven keyword suggestions

- "Get suggestions" button on `/keywords`.
- Calls `POST /api/keywords/suggest`:
  - Inputs to the LLM: current keyword list (ordered) plus the Top 10 trends from the latest completed run (title + summary text).
  - Persona context: includes Yaniv's CTO / AI-architect angle, loaded from `prompts/linkedin_system_prompt.txt` so the model judges fit against his actual voice and topic interests.
  - Model: `azure/gpt-4o` (same plumbing as `summarize()`).
- Returns array of `{keyword, reasoning}` — typically 5-8 suggestions.
- UI shows them in an inline panel below the list; each row has "Add" (creates and inserts at bottom of list, then disappears from the suggestions panel).
- Uses the existing `LLMUsageTracker`, so the call's cost is captured in the cumulative totals shown in the Summarize panels and on article-detail pages.

---

## Out of scope (keep the stage focused)

- Smart Rank (full-article fetch over top 10) — Stage 3's deferred Feature 3, will become a separate stage if/when Yaniv wants it.
- Per-source weight edits — stay in `sources.json`.
- Source enable/disable toggle in the UI — stays in `sources.json`.
- Automatic LinkedIn publishing — that's the existing "later/optional" item, now Stage 5.

## Definition of Done

- `/keywords` page exists, lists current keywords in order, supports drag-reorder, inline edit, delete, and add.
- A new manual run reflects the new ordering: items matching high-position keywords rank higher than items matching low-position keywords (verifiable by examining `rank_score` values in `/runs/{id}`).
- "Get suggestions" produces sensible LLM suggestions that match Yaniv's persona, each with a one-line reason. Clicking "Add" persists the new keyword at the bottom of the list.
- All 15 existing tests still pass; new tests cover at minimum the CRUD endpoints and the weight computation.
- One-shot seeding behavior verified: editing keywords, then re-running `init-db`, does NOT overwrite the user's list.

## Approval ritual (per CLAUDE.md)

Same as Stage 3: reads/searches auto-run; edits and git ask. Show plans before each feature, three features → three commits, separate commit/push approval. When Stage 4 is done → Yaniv approves → update `PROGRESS.md` Stage 4 to `done` → ask separately about commit.
