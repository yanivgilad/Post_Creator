# Stage 2 — Azure OpenAI provider + fully manual mode

**Goal:** Wire **Azure OpenAI** as the default generation provider so Yaniv can run the tool end to end: press "Run Now" → see a ranked feed → pick an item → generate a real LinkedIn post (Hebrew default) via Azure OpenAI. Also make the tool fully manual (no automatic scheduler).

**Branch off:** main (after the CLAUDE.md commit `fac76d9`). `pyproject.toml` already has `openai` added.

**IMPORTANT — this is Azure OpenAI, NOT direct OpenAI.** The earlier draft assumed direct OpenAI (`api.openai.com`); that was wrong and produced a 401. Yaniv's key is an Azure OpenAI key (Kaleidoo org). Azure works differently:
- Uses the `AzureOpenAI` class from the `openai` SDK (not `OpenAI`).
- Needs FOUR values, not one: API key, endpoint, deployment name, api-version.
- You call the **deployment name**, not the model name. (On Azure the deployment name is chosen by whoever set it up; here it happens to equal the model name.)

**Verified Azure details (from the working URL Yaniv already uses):**
- endpoint: `https://kaleidooazureopenai.openai.azure.com`
- deployment (for now): `gpt-4o`
- api-version: `2024-02-01`
- A second deployment `gpt-5.4` exists but its EXACT deployment name + api-version are not yet confirmed — Yaniv will get them from the org next week. **Stage 2 ships with `gpt-4o` only.** Design so adding `gpt-5.4` later is a one-line config addition, no logic change.

**Context already verified (do not re-litigate):**
- Generation is already on-demand only (`DailyPipeline.run()` builds `drafts=[]`; LLM runs only on `POST /articles` and `POST /api/articles`).
- A manual "Run Now" trigger already exists (`POST /runs/trigger`).
- Provider is blocked in TWO places: `_generate_with_provider` in `article_generator.py`, and `filter_supported_article_llm_options` in `config.py`. Both must change.
- Scheduler is ON by default via `create_app(..., start_scheduler=True)` in `cli.py`. The off-switch param already exists, just not exposed.
- Model selection is already per-request (`generate(..., llm_name)`, `_parse_model_name`).

---

## Tasks

### 1. Add the Azure OpenAI provider branch
- In `src/article_writer/generation/article_generator.py`, add a method `_generate_with_azure_openai` and wire it into `_generate_with_provider` for `provider_name == "azure"`.
- Use `from openai import AzureOpenAI`. Construct with `api_key`, `azure_endpoint`, `api_version`. Call `client.chat.completions.create(model=<deployment_name>, messages=[system, user], temperature=0.7)`.
- On Azure the `model=` argument is the **deployment name**, not a model id.
- Keep the existing `google` branch intact.

### 2. Config: support `azure/...` and read Azure settings
- In `config.py`, update `_is_supported_article_llm_option` / `filter_supported_article_llm_options` to accept `azure/...` (in addition to `google/...`).
- Add to `Settings`: `azure_openai_api_key`, `azure_openai_endpoint`, `azure_openai_api_version`, read from env (`ARTICLE_WRITER_AZURE_OPENAI_API_KEY`, `ARTICLE_WRITER_AZURE_OPENAI_ENDPOINT`, `ARTICLE_WRITER_AZURE_OPENAI_API_VERSION`).
- The part after `azure/` in the llm option IS the deployment name (e.g. `azure/gpt-4o` → deployment `gpt-4o`).
- `DEFAULT_ARTICLE_LLM_OPTIONS` = `["azure/gpt-4o", "google/gemini-2.5-pro"]`. Default selected = `azure/gpt-4o`.
- Model/deployment names stay config values, never hard-coded. Adding `azure/gpt-5.4` later = add one string to the options list + (if needed) confirm its api-version.

### 3. Azure as default; Gemini available-but-off
- Default = `azure/gpt-4o`. Gemini stays listed but not default (no key).
- **Safety:** if a selected provider is missing its required env values (key/endpoint/etc.), fail with a clear human-readable message ("Azure OpenAI is not configured — set ARTICLE_WRITER_AZURE_OPENAI_* in .env"), NOT a raw stack trace / 401.

### 4. Scheduler off by default, toggleable
- Add env flag `ARTICLE_WRITER_SCHEDULER_ENABLED` (default **false**) and/or `--no-scheduler`/`--scheduler` on `serve`, wired to `create_app(..., start_scheduler=<flag>)`. Default OFF (fully manual). Can be turned on later via flag, no code change.

### 5. Put the Azure values in `.env` (micro-step, with Yaniv)
- Add to `.env.example` (empty templates) and `.env`:
  - `ARTICLE_WRITER_AZURE_OPENAI_API_KEY=`
  - `ARTICLE_WRITER_AZURE_OPENAI_ENDPOINT=`
  - `ARTICLE_WRITER_AZURE_OPENAI_API_VERSION=`
- Yaniv fills the real values into `.env` himself (key + endpoint `https://kaleidooazureopenai.openai.azure.com` + api-version `2024-02-01`). **Never in chat, never in git.** Confirm `.env` is gitignored (already verified: `.gitignore:4`).
- The OpenAI direct key var added earlier (`ARTICLE_WRITER_OPENAI_API_KEY`) can stay as an empty unused template or be removed — Yaniv's call; not required for Azure.

### 6. (Docs) reflect reality
- Update `docs/ARCHITECTURE.md` and `CLAUDE.md` briefly: provider is **Azure OpenAI** (default deployment `gpt-4o`), Gemini available-but-off; scheduler OFF by default (manual via "Run Now" / `run-once`).

## Not in this stage (deferred)
- `gpt-5.4` deployment — added next week once Yaniv confirms its exact deployment name + api-version.
- A separate cheaper model for summaries — Stage 3, with the summary action itself (no LLM summary exists today; model selection is already per-request, so it's easy later).
- Internal "full summary" / "read article" view — Stage 3.

## Definition of Done
- `azure` provider branch works in `article_generator.py`; `google` branch intact.
- `config.py` accepts `azure/...`; `azure/gpt-4o` is default; Gemini still listed.
- Missing Azure config → clear error, not a crash/401.
- Scheduler OFF by default; enableable via flag without code change.
- Azure values in `.env` (gitignored), not in git or chat.
- **End-to-end (the deferred Stage 1 test):** Yaniv installs deps (`py -m pip install -e .`), runs `serve`, presses "Run Now", sees a ranked feed, picks an item, generates a LinkedIn post in Hebrew via Azure `gpt-4o`, and confirms it sounds like him. This is the real milestone.

## Approval ritual (per CLAUDE.md)
Show diffs before each edit. When done → Yaniv reviews → updates Stage 2 status to `done` in PROGRESS.md → Claude asks separately about commit+push (show `git status` + proposed message) → commit → push → fresh chat for Stage 3.
