# Stage 3 — UX sharpening: RTL + on-demand summary

**Goal:** Make the read-and-post flow sharper. Originally three features; Smart Rank was de-scoped mid-stage by Yaniv (see end of this file). Final delivered scope:
1. Hebrew renders right-to-left in the dashboard (cosmetic fix).
2. On-demand article summary (a button that generates a short summary of an item).
3. ~~Smart ranking run~~ — **de-scoped, deferred to a future stage.**

**Branch off:** main (after Stage 2 commit `3511df5`).

**Provider context (from Stage 2):** Azure OpenAI, default deployment `gpt-4o`. Only `gpt-4o` is available right now; `gpt-5.4` comes later. Model selection is already per-request (`generate(..., llm_name)`, `_parse_model_name`). The Yaniv persona lives in `prompts/*.txt` and already encodes his CTO-positioning angle and topic interests — the smart-ranking model should use that same context to judge "fit for Yaniv", not a generic ranking.

**Permissions note:** reads/searches/git-status now auto-run; edits, deletes, and git commit/push still prompt. Move fast on safe steps, pause on the ones that change code or history.

---

## Feature 1 — RTL display (small, do first)
- In the dashboard templates/CSS (`web/`), make Hebrew content render right-to-left. The generated post body and the feed items currently render left-aligned.
- Simplest correct approach: set `direction: rtl` / `text-align: right` on the containers that hold Hebrew (or detect direction per content). Don't break the English/LTR parts of the UI.
- This is cosmetic only — the stored text is already correct. Pure CSS/template change.

## Feature 2 — On-demand summary
- Add a "Summarize" action on a feed item that calls the LLM to produce a SHORT summary (a few sentences) of the item, shown in the UI.
- Reuse the existing per-request model plumbing — the summary call passes its own `llm_name`. For now it uses `azure/gpt-4o` (only deployment available); keep it cheap by making the summary prompt explicitly short (low output tokens). When a cheaper deployment (e.g. `gpt-5.4` or a mini) is added later, the summary can switch to it via config — no logic change.
- This is the FIRST LLM summary action in the project (today the feed `summary` is raw from the source). New endpoint/route + a generation method `summarize(...)`.
- Keep it on-demand only (button press), never automatic — consistent with the cost-conscious manual model.

## Feature 3 — Smart ranking run (the big one)
- Add a "Smart Rank" trigger (button) that runs AFTER a normal fetch+rank, over the **top-10** ranked items.
- For each of the 10: fetch the FULL article text from its link, send it to the model (Azure `gpt-4o`), and get back: (a) a short summary, (b) a "worth-turning-into-a-post" score, (c) a one-paragraph explanation of WHY — judged for FIT WITH YANIV (use the persona context: his CTO positioning, his topics, his angle).
- Present the 10 results re-ordered by the model's score, each with its summary + explanation, so Yaniv can quickly decide what to write about.
- **Full-text fetch with graceful fallback:** fetching the article body can fail (paywalls, blocked bots, arXiv PDFs, dead links). If fetch fails for an item, fall back to its title + source summary and mark it as "ranked on title/abstract only" so Yaniv knows. NEVER let one failed fetch break the whole run.
- **Cost/time honesty:** this is the slowest, most expensive action in the tool (10 full articles → model). Expect ~1-2 min and a few cents per run. It's a deliberate, occasional action, not something to spam. Show a progress/live-log like the normal run does.
- Reuse the per-request model plumbing so the smart-rank model is configurable (default `azure/gpt-4o`).

---

## Out of scope (keep the stage focused)
- Automatic publishing to LinkedIn (that's the separate "Stage 4" idea in PROGRESS.md).
- Adding `gpt-5.4` — separate one-line config add when Yaniv has its deployment name.
- Switching summary/smart-rank to a cheaper model — trivial later once a cheaper deployment exists.

## Definition of Done (as delivered)
- Hebrew renders RTL in the dashboard; English UI parts unaffected. ✅
- A "Summarize" button produces a short LLM summary of an item, on demand, via Azure. ✅
- Nothing runs automatically; both are manual/on-demand. ✅
- Bonus delivered: per-call token/cost displayed and cumulative cost persisted across summarize + article-generation calls.
- ~~Smart Rank end-to-end check~~ — de-scoped, see note below.

## Mid-stage scope change

After Features 1 and 2 plus cost tracking landed, Yaniv chose to **de-scope Feature 3 (Smart Rank)**. The reason: Smart Rank would be the slowest and most expensive action in the tool (10 full-article fetches + 10 LLM calls per run, ~1-2 minutes, a few cents per click), and the marginal value over the existing source-weight + freshness ranking did not justify the cost in his current workflow. If reintroduced it will be its own stage with its own spec.

## Approval ritual (per CLAUDE.md)
Reads/searches auto-run now. Show diffs before edits; ask before commit/push (separate from stage approval). Suggested internal order: Feature 1 (RTL) → commit → Feature 2 (summary) → commit → Feature 3 (smart rank) → commit. Three small commits keep it clean and let Yaniv stop between features. When the stage is done → Yaniv approves → update PROGRESS.md Stage 3 to done → ask separately about commit.
