# Prompt for the v2 fork agent

Copy the entire block between the `---BEGIN PROMPT---` and `---END PROMPT---`
markers below into a new Claude Code session started from this workspace.

---BEGIN PROMPT---

You are building **v2** of the Healthcare Roster Scheduler: a React SPA +
FastAPI rewrite of the existing Streamlit app, shipped on a new git branch
of this same GitHub repo, deployed as a **separate** Hugging Face Space. The
existing `scheduler/` Python package is proven; you will reuse it verbatim.

## 1. Read first, in this order

Before you do anything else:

1. **`docs/NEW_UI_PLAN.md`** — the authoritative plan. Self-contained,
   ~850 lines. Tech stack, architecture, API contract, page-by-page UX,
   feature-parity matrix, phase sequencing, dependencies, Dockerfile,
   migration notes. **Follow it.**
2. `docs/FEATURES.md` — the v0.7.1 feature reference. You must reach parity
   with everything here.
3. `docs/CONSTRAINTS.md` — the formal constraint spec. If you think a
   constraint is wrong, escalate before changing `scheduler/`.
4. `docs/CHANGELOG.md` — release history, so you know what's shipped.
5. `app.py` — the current Streamlit app. Skim it to understand how the
   existing UI uses `scheduler/`; don't copy its patterns.

## 2. Before you write any code, ask me

Get answers to every open question listed in **NEW_UI_PLAN.md §12**:

1. New HF Space name (default suggestion: `doctor_roster_v2`).
2. Branch name (default suggestion: `react-ui`).
3. Dark-mode default (default: off).
4. Calendar library licence — FullCalendar Standard (MIT) vs
   `react-big-calendar`. Default: FullCalendar.
5. Session persistence — localStorage + manual YAML download/upload only,
   or a mounted volume? Default: localStorage only.
6. App-level auth — none vs a password gate? Default: none (rely on HF
   Space sharing controls).

If I don't answer within a message or two, proceed with the defaults and
tell me what you chose.

## 3. Hard rules

- **Do not modify `scheduler/`.** If you're tempted, escalate first. The
  right answer is almost always to work around it in the API layer.
- **Do not modify the existing tests.** Add new ones for the API layer;
  keep `tests/test_smoke.py`, `tests/test_h11.py`, `tests/test_stress.py`
  green.
- **Do not touch the `main` branch.** All work is on the new branch. Push
  to GitHub `origin` **and** to the new HF Space remote.
- **Do not introduce authentication, accounts, or cloud storage.** v2 is a
  UI rewrite, not a product pivot.
- **Docker SDK only** on HF (same as v1). Port 7860. Frontmatter goes in
  the branch's `README.md` just like the main branch.

## 4. Execute phases 0 → 9 from NEW_UI_PLAN.md §10

At each phase boundary:

1. Run `pytest tests/ -x -q` and confirm it passes.
2. Commit with a clear message referencing the phase number.
3. Push to GitHub `origin` and to the HF Space remote.
4. Verify the HF Space rebuilds to `RUNNING` stage before starting the
   next phase.

Use `TodoWrite` to track the 10 phases + any sub-tasks you discover.

## 5. HF Space deployment pattern

The token-push pattern is saved in memory. Summary:

- The user's HF access token lives in `.hf_access_token` at the repo
  root. `.gitignore` already excludes it.
- To push to the new HF Space remote, use the same inline-URL +
  `sed`-redact pattern saved in memory under `hf_token_usage.md`. Ask the
  user for the new Space's URL once they've named it (§2.1).
- Poll `https://huggingface.co/api/spaces/<user>/<name>` with a Bearer
  token to confirm `runtime.stage == "RUNNING"` and `sha` matches HEAD.

## 6. Communication rhythm

- **Ask** before starting any phase that deviates from NEW_UI_PLAN.md.
- **Announce** before each phase ("Starting Phase 3 — Setup page"), and
  **summarise** after ("Phase 3 done. Doctors table has inline edit,
  chip-based station eligibility, keyboard nav. Commit `<sha>`. HF
  rebuild RUNNING.").
- **Escalate immediately** on:
  - Anything that requires changing `scheduler/`.
  - Anything that requires changing `docs/CONSTRAINTS.md`.
  - A feature-parity gap you can't close without a new dependency.
  - CP-SAT behaving differently under the new invocation path.
- Keep intermediate explanations short (≤100 words). I'll ask if I need
  more detail.

## 7. Success criteria — reach these before calling v2 done

Verbatim from **NEW_UI_PLAN.md §13**:

1. Open the Space on a desktop browser, load a saved YAML, solve a 30-
   doctor × 28-day roster, drag one cell to move an assignment, re-solve
   around it, and export a PDF — without ever waiting for the page to
   reload.
2. Open the same Space on a phone, check who's on call for the next 3
   days in under 10 seconds.
3. Produce next month's roster by cloning last month's YAML, uploading
   last month's JSON to auto-fill `prev_workload`, editing dates and new
   leave, and solving — in under 5 minutes of active work.

## 8. First three things to do in this session

1. Read `docs/NEW_UI_PLAN.md` in full.
2. Ask me the §12 open questions in a single message.
3. Wait for my answers, then start **Phase 0 — Scaffolding** (branch
   creation, `api/` and `ui/` scaffolds, placeholder SPA returning 200,
   new HF Space created and building).

Do not proceed past Phase 0 without a green HF Space build.

---END PROMPT---
