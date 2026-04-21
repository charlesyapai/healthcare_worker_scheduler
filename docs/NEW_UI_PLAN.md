# New UI Plan — Healthcare Roster Scheduler v2

Hand-off document for the agent that will fork a new branch and build a
non-Streamlit UI for this project.

---

## 0. Brief for the forking agent

**Your job:** on a new branch of this repo, replace the Streamlit app with a
modern web UI (React SPA + FastAPI backend) while **reusing the entire
`scheduler/` Python package verbatim**. Deploy as a new, separate Hugging
Face Space.

**What to preserve:**

- `scheduler/` — the solver, instance model, diagnostics, metrics,
  persistence, plots. This is the proven core; do not rewrite it.
- `docs/CONSTRAINTS.md`, `docs/FEATURES.md`, `docs/CHANGELOG.md` — you will
  add v2-specific addendums but the spec is unchanged.
- `tests/` — the existing pytest suite should still pass against the new
  backend.

**What to replace:**

- `app.py` — the Streamlit entrypoint. Becomes a thin FastAPI app that
  imports the same `scheduler/` functions.
- The entire user-facing UI — built fresh as a React SPA served by FastAPI.

**Things the user will tell you before you start:**

1. New HF Space name (e.g. `doctor_roster_v2` or similar).
2. Branch name (suggestion: `react-ui`).
3. Whether to keep or drop the benchmark CLI (`scheduler/benchmark.py`) —
   recommend keep; it doesn't affect the app.

**Things you should NOT do:**

- Don't re-derive the constraint logic. `scheduler/model.py` is the source
  of truth. If you think a constraint is wrong, raise it with the user
  before modifying.
- Don't bundle a separate solver. CP-SAT via OR-Tools is the standard.
- Don't introduce user auth / accounts. HF Spaces handles the surrounding
  identity layer; the app itself is single-user (same as v1).

---

## 1. Goals

The v1 Streamlit app (branch `main`) is functionally complete — every rule,
weight, toggle, and view is wired up. The problem is **UX ceilings that
Streamlit imposes**:

1. Clumsy data-table editing (cell-commit races, no drag to resize columns,
   no sticky headers on long tables).
2. No drag-and-drop cell-level roster editing.
3. Blocking while-loops or the brittle `st.rerun()` async pattern for
   live streaming.
4. Single-column, desktop-only layout; mobile is unusable.
5. No proper modal dialogs, context menus, or keyboard shortcuts.
6. Forms rebuild on every interaction, dropping in-flight state.
7. No way to render a roster grid as a **real calendar** with day cards.

The v2 goals:

- **Roster coordinator** opens the app and can do a full monthly cycle —
  configure, solve, publish — without fighting the UI.
- **Edit assignments in-place** by clicking cells, swapping doctors,
  dragging between days.
- **Live solver progress** that feels smooth (no whole-page reruns).
- **Mobile-usable** for quick checks ("who's on call tonight?").
- **Keyboard-friendly** for rosterers who do this weekly.
- **Calendar-first** visual language — this is a scheduling app, the UI
  should look like a calendar.

---

## 2. Tech stack

### 2.1 Frontend

| Layer | Choice | Rationale |
|---|---|---|
| Framework | **React 18 + TypeScript** | Biggest ecosystem; AI assistants are most productive here. |
| Build | **Vite** | Fast dev server and builds; zero config. |
| Styling | **Tailwind CSS 4** | Predictable, composable, no CSS files to manage. |
| Component lib | **shadcn/ui** (Radix UI + Tailwind) | Accessible, copy-into-repo components, not a locked-in library. |
| State — server | **TanStack Query (React Query) v5** | Cache, refetch, mutations, devtools. |
| State — client | **Zustand** | Tiny, un-opinionated, no boilerplate. |
| Forms | **React Hook Form + Zod** | Validation-first, tiny bundle. |
| Tables | **TanStack Table v8** | Headless — drive any visual, supports inline edit, sticky headers. |
| Drag-and-drop | **dnd-kit** | Accessible, works with keyboards, small. |
| Calendar view | **FullCalendar** (premium not needed) | Proven grid calendar with keyboard nav. |
| Icons | **lucide-react** | Consistent, tree-shakeable. |
| Notifications | **sonner** | Stacking toasts with built-in a11y. |
| Date handling | **date-fns** | Pure functions, immutable, no Moment. |
| Routing | **React Router v6** | Tabs as URL routes so you can share links. |
| Real-time | **native WebSocket** | Built into browsers; see §4.3. |

### 2.2 Backend

| Layer | Choice | Rationale |
|---|---|---|
| Framework | **FastAPI** | Async, WebSocket native, auto OpenAPI docs. |
| Server | **Uvicorn** | Standard FastAPI production runner. |
| Validation | **Pydantic v2** | Ships with FastAPI; mirrors Zod schemas. |
| Solver | **`scheduler/` package** (reused verbatim) | Already tested. |
| Serialization | **orjson** via FastAPI | Faster JSON for the big roster payloads. |
| File storage | **in-memory per-session** | No disk writes; HF Spaces are ephemeral. |

### 2.3 Dev tooling

- **pnpm** for Node package management (faster + smaller than npm).
- **ESLint + Prettier** via shadcn/ui defaults.
- **TypeScript strict mode** end to end.
- **Vitest** for frontend unit tests (optional; page-level Playwright later).
- **pytest** for backend — already exists.

### 2.4 Why not alternatives

- **Gradio** — marginally nicer than Streamlit for some patterns but still
  server-rendered with the same rerun model. Not a leap in UX.
- **NiceGUI / Reflex** — Python-native, event-driven. Better than Streamlit.
  But you still can't write a custom calendar grid or fluid drag-and-drop
  without dropping into JS. If we're adding JS, go all the way.
- **HTMX + FastAPI + Tailwind** — viable, faster iteration than React for
  simple forms. But a roster editor needs client-side state (drag state,
  selection, undo), and HTMX is awkward there.
- **SvelteKit** — genuinely nicer developer experience than React, but
  smaller ecosystem for data-grids and calendars. AI tooling is weaker.
- **Streamlit 1.45 with custom components** — patches the symptoms without
  fixing the model.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Browser (SPA)                          │
│  React + TS + Tailwind + shadcn/ui                        │
│  • Pages: /setup /rules /solve /roster /export            │
│  • State: TanStack Query (server) + Zustand (client)      │
│  • Calendar: FullCalendar  Table: TanStack Table          │
│  • DnD: dnd-kit                                           │
└─────────────┬──────────────────────────────┬──────────────┘
              │  REST JSON                    │  WebSocket
              │  (TanStack Query)             │  (solve stream)
┌─────────────▼──────────────────────────────▼──────────────┐
│                   FastAPI (uvicorn)                        │
│  • /api/config     GET/PUT  JSON <--> YAML on disk         │
│  • /api/instance   POST     build Instance (validate only) │
│  • /api/solve      WS       stream solve events            │
│  • /api/overrides  POST     copy roster → overrides        │
│  • /api/diagnose   POST     L1 checks                      │
│  • /api/explain    POST     L3 relaxed solve               │
│  • Static: /         → SPA built assets                    │
└─────────────┬──────────────────────────────────────────────┘
              │ Python function calls
┌─────────────▼──────────────────────────────────────────────┐
│                 scheduler/ (UNCHANGED)                     │
│  instance • model • diagnostics • metrics • persistence    │
│  plots (used by API endpoints that return chart data)      │
└────────────────────────────────────────────────────────────┘
```

**Session model**: one in-memory session per browser tab, keyed by a
cookie `session_id`. Session holds the current `Instance`, last result,
intermediate events. Backend is stateless-ish — restart wipes all sessions.
The user can always `Save YAML` to persist.

---

## 4. API design

All endpoints return JSON. Use OpenAPI-driven type generation: run
`openapi-typescript` against `/openapi.json` to produce `src/api/types.ts`
so the frontend and backend can't drift.

### 4.1 REST endpoints

```
GET  /api/state             → full SessionState { doctors, stations, blocks,
                              overrides, weights, hours, constraints,
                              tier_labels, subspecs, horizon }

PUT  /api/state             body: SessionState
                            Replace entire state (idempotent).

PATCH /api/state            body: partial SessionState
                            Deep-merge specific fields.

POST /api/state/yaml        body: { yaml: string }
                            Server-side load_state(); returns new SessionState.

GET  /api/state/yaml        → { yaml: string }
                            Server-side dump_state().

POST /api/state/prev_workload
                            body: { prev_roster_json: object }
                            Returns updated doctors[] with prev_workload filled.

POST /api/diagnose          → FeasibilityIssue[]         (L1 pre-solve)
POST /api/explain           → InfeasibilityReport        (L3 soft-relax)

POST /api/overrides/fill-from-snapshot
                            body: { snapshot_id: string | "final" }
                            Dumps the chosen snapshot into the overrides list.
                            Returns the new overrides array.
```

### 4.2 Solve — WebSocket

```
WS /api/solve
→ client sends { action: "start", snapshot_assignments: true }
← server streams
   { type: "event", wall_s, objective, best_bound, components, assignments }
   … (one per improving solution) …
   { type: "done", result: SolveResult }
   or
   { type: "error", message: "..." }

→ client may send { action: "stop" } to trigger StopSearch().
```

This maps directly onto the existing `solve(..., on_intermediate=...,
stop_event=...)` contract — no solver changes needed.

### 4.3 Where the Streamlit data-editor complexity goes

- **No more `key=` races.** The SPA owns editable state in its own store;
  backend just accepts the final object.
- **No more reassignment loops.** Each mutation is a single `PUT`/`PATCH`
  with the full resulting array. Optimistic updates via TanStack Query.
- **No more `st.rerun()`**. WebSocket pushes events, React subscribes.

---

## 5. UI / UX — page by page

URL-driven tabs so a rosterer can bookmark the roster view, share the URL
with a colleague, etc.

### 5.1 `/` — Dashboard

Landing page. Shows:

- Current status: "You have 12 doctors configured, 3 blocks, 1 solve run."
- Big buttons: **Solve now**, **Edit setup**, **Open last roster**.
- Quick stats: horizon, tier breakdown, known issues from L1.

Empty-state: "Click **Load YAML** to restore a previous config, or start
with the defaults."

### 5.2 `/setup` — Per-period inputs

Four collapsible cards (all open by default, remember state locally):

1. **When** — inline date-range picker + public holidays as chips.
2. **Doctors** — a proper spreadsheet-like table (TanStack Table):
   - Sticky header, resizable columns.
   - Inline editing with validation on blur.
   - Keyboard: Tab / Shift-Tab / Enter to navigate.
   - "+" button at top, context menu for delete.
   - Clipboard: Ctrl+V pastes multi-row data; Ctrl+C copies selection.
   - FTE as a number input with a visual slider (0.1–1.0).
   - Multi-select "Eligible stations" chips (not comma-separated text).
3. **Leave, blocks, and preferences** — **two sub-views**:
   - **Calendar view** (FullCalendar, default): month grid, click a day
     to add a block for the selected doctor; drag a block to extend
     its span; right-click to delete.
   - **Table view**: traditional row editor for bulk operations.
   - Switch between the two with a toggle.
   - CSV paste still available in a drawer.
4. **Manual overrides** — table view. Filter by doctor / date. Delete
   button per row. "Clear all" with confirmation.

### 5.3 `/rules` — Department rules

Same seven sections as v1, but as **tabs within the page** not a long
scroll. URLs like `/rules/tiers`, `/rules/stations`, etc.

- **Stations editor** — cards per station (not one long table). Each card
  shows a mini-diagram: `[AM] [PM]` chips, eligible-tier badges, required
  headcount. Click to edit inline.
- **Rules toggles** — segmented control + inline parameter for H4's N.
- **Hours per shift** — table with inline editing; visual bar chart to
  the right showing relative lengths.
- **Workload weights + Solver priorities** — two-column layout with live
  preview ("A weekend on-call is worth {w_we_oncall}; current = 35").

Changes here write to `/api/state` with `PATCH`. No save button needed —
debounced auto-save at 500ms. Toast on success.

### 5.4 `/solve` — Run the solver

Left rail: solver settings (time limit, workers, feasibility-only, stop
button). Centre: live view during solve — progress bar, convergence
chart (recharts or Plotly), intermediate-solutions table. Right rail:
current-best roster thumbnail + metric strip.

**During solve**:

- Progress bar shows elapsed/time-limit + "n solutions found".
- Convergence chart updates via WebSocket (~5 fps).
- Verdict banner at top appears once the first feasible is found.

**Stop button**: sends `{ action: "stop" }` on the WebSocket; immediately
disables to prevent double-click.

### 5.5 `/roster` — Review and edit

This is the **payoff screen** — must feel great.

Three view modes, switchable via URL tabs:

1. **Calendar grid** (default) — FullCalendar week/month views. Each day
   cell shows assignments as colour-coded chips. Click a chip to edit;
   drag a chip to move to another day.
2. **Doctor × date heatmap** — the v1 grid, but prettier. Sticky doctor
   column, sticky date header. Colour by role, tooltip on hover with
   full role detail.
3. **Station × date** — transposed grid; rows are station·session.

**Cell editing workflow**:

- Click a cell → popover with the list of eligible doctors for that
  slot, plus "remove" option.
- Changes commit optimistically; server validates in background.
- If validation fails, toast + undo.

**Lock-and-re-solve**:

- Select cells (shift-click for range, ctrl-click for individual).
- Click "🔒 Lock selected" → adds them to overrides.
- Click "▶ Re-solve" to re-run with those overrides.
- Diff view shows what changed.

**Workload panel** (right side):

- Headline table (Doctor / Tier / Score / Δ median / Hours / Idle).
- Click a doctor row → per-doctor calendar in a drawer.
- Cross-tier hours summary at top.

**Snapshot picker** at top: slider across all intermediate solutions, not
a dropdown. Scrub to any solution, the grid updates live.

### 5.6 `/export` — Publishing

- **Download** dropdown: JSON / CSV / HTML / ICS calendar file.
- **Print preview** pane — renders exactly what the PDF will look like;
  Ctrl+P prints.
- **Per-doctor emails**: preview + mailto link for each doctor's schedule
  (no actual SMTP; user copies into their mail client).
- **Shareable snapshot**: "Copy link" button that encodes the current
  state into a URL query string (Base64-compressed) so two rosterers can
  share a roster draft without a server.

### 5.7 Global layout

- Top bar: logo, current horizon label, "Save YAML" button, solver
  settings gear, dark-mode toggle.
- Left nav: Setup · Rules · Solve · Roster · Export (icons + labels).
- Responsive: left nav collapses to a bottom-tab-bar on mobile; roster
  grid becomes horizontally scrollable with a sticky doctor column.
- Keyboard shortcuts: `g s` → Setup, `g r` → Rules, `g o` → Roster,
  `g e` → Export. `Ctrl+Enter` → Solve. `Ctrl+S` → Save YAML.

---

## 6. Feature parity matrix

Everything in v0.7.1's `docs/FEATURES.md` must work in v2. Item-by-item:

| v1 feature | v2 treatment |
|---|---|
| Four tabs (Setup / Dept rules / Solve & Roster / Export) | Kept as pages. |
| Save / Load YAML | Kept, same endpoint on backend. Frontend adds "recent files" list. |
| Import prior-period workload | Kept, with drag-drop zone instead of a file uploader. |
| Tier labels + sub-specs edit | Kept in `/rules`. |
| Doctor table with FTE, max_oncalls, prev_workload, eligible_stations | Kept — now a real spreadsheet. Eligible stations = multi-select chips. |
| Stations editor | Kept as card grid. |
| Blocks table (Leave / No on-call / No AM / No PM / Prefer AM / Prefer PM) | Kept; adds calendar view. |
| CSV paste for blocks | Kept as a drawer. |
| Multi-day leave (end_date column) | Kept; calendar view shows as a multi-day span visually. |
| Manual overrides | Kept; adds "generate from snapshot" button. |
| Constraint toggles (H4 N, H5–H11) | Kept. |
| Hours per shift | Kept. |
| Workload weights | Kept. |
| Solver priorities | Kept. |
| Live solve streaming | WebSocket instead of st.rerun loop. |
| Stop button | Kept, wired to WebSocket. |
| Verdict banner | Kept. |
| Metric strip (status / time / days-without-duty / avg hours per tier / penalty) | Kept. |
| Snapshot picker | Slider, not dropdown. |
| Colour-coded roster grid | Kept, visual polish. |
| Per-doctor workload headline | Kept. |
| Per-doctor workload breakdown | Kept as drawer. |
| Alternative views (station × date, per-doctor cal, today's roster) | Kept as view-mode toggle on `/roster`. |
| Diff snapshots | Kept as a side-by-side view. |
| Advanced analytics (convergence etc.) | Kept as a dedicated `/analytics` sub-page. |
| L1 / L3 diagnostics | Kept as modals. |
| Export JSON / CSV / HTML | Kept. |
| Copy-this-roster-to-overrides | Kept, integrated into `/roster` (see §5.5). |

---

## 7. New features enabled by better UI

Things Streamlit couldn't do that v2 should ship:

1. **Drag-and-drop cell editing** on the roster grid.
2. **Calendar view for leave/blocks** (click day, drag to extend).
3. **True mobile layout** with a sticky column on the roster grid.
4. **Keyboard shortcuts** for fast editing.
5. **Shareable URLs** for draft rosters (no login needed).
6. **Undo/redo** within a session (state is client-side, easy to stack).
7. **"Today's roster"** as a widget on the top bar, always visible.
8. **Dark mode** (nice on 10pm WhatsApp checks).
9. **Notifications toast queue** — doesn't block the view like Streamlit's
   `st.error` does.
10. **ICS calendar export** — doctors subscribe to a `.ics` feed of their
    roster.
11. **Per-doctor email previews** with mailto: links (not a full email
    client but saves copy-paste).
12. **Auto-save** of the session to localStorage — survives browser refresh
    without forcing a YAML download.

Out of scope for v2 (still): real-time multi-user, actual SMTP, auth,
server-side persistence across deploys.

---

## 8. Dependencies

### 8.1 Frontend — `package.json`

```json
{
  "name": "doctor-roster-ui",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "lint": "eslint . --ext .ts,.tsx",
    "format": "prettier --write src"
  },
  "dependencies": {
    "@fullcalendar/core": "^6",
    "@fullcalendar/daygrid": "^6",
    "@fullcalendar/interaction": "^6",
    "@fullcalendar/react": "^6",
    "@fullcalendar/timegrid": "^6",
    "@hookform/resolvers": "^3",
    "@radix-ui/react-*": "latest (as pulled in by shadcn/ui)",
    "@tanstack/react-query": "^5",
    "@tanstack/react-table": "^8",
    "@dnd-kit/core": "^6",
    "@dnd-kit/sortable": "^8",
    "class-variance-authority": "^0.7",
    "clsx": "^2",
    "date-fns": "^3",
    "js-yaml": "^4",
    "lucide-react": "^0.400",
    "react": "^18",
    "react-dom": "^18",
    "react-hook-form": "^7",
    "react-router-dom": "^6",
    "recharts": "^2",
    "sonner": "^1",
    "tailwind-merge": "^2",
    "zod": "^3",
    "zustand": "^4"
  },
  "devDependencies": {
    "@types/js-yaml": "^4",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "@vitejs/plugin-react": "^4",
    "autoprefixer": "^10",
    "eslint": "^9",
    "eslint-config-prettier": "^9",
    "eslint-plugin-react": "^7",
    "eslint-plugin-react-hooks": "^4",
    "openapi-typescript": "^7",
    "postcss": "^8",
    "prettier": "^3",
    "tailwindcss": "^4",
    "typescript": "^5",
    "vite": "^5",
    "vitest": "^2"
  }
}
```

### 8.2 Backend — new `requirements.txt` additions

```
# Existing (unchanged)
ortools>=9.10
PyYAML>=6.0
pandas>=2.0
plotly>=5.20

# New (replaces streamlit)
fastapi>=0.115
uvicorn[standard]>=0.30
orjson>=3.10
python-multipart>=0.0.9    # for file uploads
websockets>=12             # WS transport

# Dev
pytest>=8
httpx>=0.27                # for FastAPI test client
```

Remove: `streamlit`.

### 8.3 Deployment — `Dockerfile`

Multi-stage so the frontend build doesn't end up in the runtime image.

```dockerfile
# ───── Stage 1: build SPA ─────
FROM node:20-alpine AS web
WORKDIR /web
COPY ui/package.json ui/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY ui/ ./
RUN pnpm build                   # emits /web/dist

# ───── Stage 2: Python runtime ─────
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY scheduler/ ./scheduler/
COPY api/ ./api/
COPY --from=web /web/dist ./api/static
EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

HF Spaces Docker frontmatter on the README stays the same:

```
---
title: Doctor Roster v2
emoji: 🩺
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
---
```

---

## 9. Project structure

```
/ (repo root, branch: react-ui)
├── README.md              # v2 intro + HF frontmatter
├── Dockerfile             # multi-stage (see §8.3)
├── requirements.txt       # backend deps
├── pyproject.toml         # optional, for editable installs
├── docs/
│   ├── NEW_UI_PLAN.md     # THIS FILE (kept for reference)
│   ├── FEATURES.md        # inherited; update with v2-specific notes
│   ├── CONSTRAINTS.md     # unchanged
│   ├── CHANGELOG.md       # append v2 entries
│   └── CONTEXT.md         # append v2 entries
├── scheduler/             # UNCHANGED from main branch
│   ├── __init__.py
│   ├── instance.py
│   ├── model.py
│   ├── diagnostics.py
│   ├── metrics.py
│   ├── persistence.py
│   ├── plots.py
│   ├── ui_state.py
│   └── benchmark.py
├── api/                   # NEW — FastAPI app
│   ├── __init__.py
│   ├── main.py            # FastAPI app + static mount
│   ├── routes/
│   │   ├── state.py       # GET/PUT/PATCH /api/state
│   │   ├── yaml.py        # import/export YAML
│   │   ├── solve.py       # WebSocket + overrides
│   │   ├── diagnostics.py # L1 + L3 endpoints
│   │   └── export.py      # JSON/CSV/HTML/ICS download
│   ├── models/            # Pydantic request/response schemas
│   │   ├── session.py
│   │   └── events.py
│   ├── sessions.py        # in-memory session store (cookie-keyed)
│   └── static/            # populated at build time (webui dist)
├── ui/                    # NEW — React SPA source
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   ├── public/
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/
│       │   ├── Dashboard.tsx
│       │   ├── Setup/
│       │   │   ├── index.tsx
│       │   │   ├── When.tsx
│       │   │   ├── Doctors.tsx
│       │   │   ├── Blocks.tsx        # includes calendar + table
│       │   │   └── Overrides.tsx
│       │   ├── Rules/
│       │   │   ├── index.tsx
│       │   │   ├── Tiers.tsx
│       │   │   ├── Stations.tsx
│       │   │   ├── Toggles.tsx
│       │   │   ├── Hours.tsx
│       │   │   ├── Fairness.tsx
│       │   │   └── Priorities.tsx
│       │   ├── Solve.tsx
│       │   ├── Roster/
│       │   │   ├── index.tsx
│       │   │   ├── Calendar.tsx
│       │   │   ├── Heatmap.tsx
│       │   │   └── StationView.tsx
│       │   └── Export.tsx
│       ├── components/       # shadcn/ui + custom
│       │   ├── ui/          # shadcn generated
│       │   ├── RosterCell.tsx
│       │   ├── WorkloadTable.tsx
│       │   ├── ConvergenceChart.tsx
│       │   └── ... etc.
│       ├── api/
│       │   ├── client.ts    # fetch wrapper + query keys
│       │   ├── types.ts     # generated from /openapi.json
│       │   └── ws.ts        # solve WebSocket client
│       ├── store/
│       │   ├── session.ts   # Zustand store mirror of backend state
│       │   ├── solveStatus.ts
│       │   └── undo.ts
│       ├── lib/
│       │   ├── dates.ts
│       │   ├── colors.ts
│       │   └── keys.ts      # keyboard shortcut map
│       └── styles/
│           └── globals.css
└── tests/
    ├── test_smoke.py         # inherited
    ├── test_h11.py           # inherited
    ├── test_stress.py        # inherited
    ├── test_api_state.py     # NEW — FastAPI endpoints
    └── test_api_solve.py     # NEW — WebSocket streaming
```

---

## 10. Implementation phases

**Don't try to ship all of this at once.** Sequence so you have a
deployable app at the end of each phase.

### Phase 0 — Scaffolding (0.5 day)

- Create branch `react-ui` from `main`.
- Add `api/`, `ui/` directories, update `Dockerfile`.
- Replace `app.py` with a shim `api/main.py` that mounts a placeholder SPA.
- New HF Space pointing at the branch. Confirm Docker build + RUNNING.

**Deliverable**: 200 OK landing page from the new Space.

### Phase 1 — Backend API (2–3 days)

- Pydantic models mirroring session state.
- Implement `/api/state` GET/PUT/PATCH with in-memory store.
- Implement `/api/state/yaml` import/export (reuses
  `scheduler.persistence`).
- Implement `/api/diagnose` + `/api/explain` (L1 + L3).
- Implement `/api/solve` WebSocket (reuses
  `scheduler.model.solve` with streaming callback).
- Add `tests/test_api_state.py`, `tests/test_api_solve.py`.
- Generate `ui/src/api/types.ts` from `/openapi.json`.

**Deliverable**: all functionality exposed over HTTP, tested, with typed
client.

### Phase 2 — SPA foundations (2 days)

- Vite + React + TS + Tailwind + shadcn/ui setup.
- Router with placeholder routes `/setup /rules /solve /roster /export`.
- API client (TanStack Query) + session store (Zustand).
- Basic layout: top bar, left nav, dark mode, toasts.

**Deliverable**: navigable empty shell that talks to the backend.

### Phase 3 — Setup page (2–3 days)

- Dates card.
- Doctors table (TanStack Table with inline edit).
- Blocks table (tabular only, no calendar yet).
- Overrides table.
- CSV paste drawer.
- Auto-save via debounced PATCH.

**Deliverable**: can configure a problem fully via the SPA.

### Phase 4 — Department rules page (1–2 days)

- Tabs: Tiers / Sub-specs / Stations / Rules / Hours / Fairness / Priorities.
- Stations as card grid.
- Other sections: forms with sensible inputs (segmented controls, sliders
  for weights, etc.).

**Deliverable**: every configurable knob available.

### Phase 5 — Solve page (2 days)

- WebSocket client.
- Live progress bar + convergence chart (recharts).
- Stop button.
- Verdict banner.
- Write solve results to session state, enabling `/roster`.

**Deliverable**: can solve end to end and see results.

### Phase 6 — Roster page (3–4 days)

- Doctor × date heatmap view (the v1 grid, better).
- Workload table.
- Snapshot picker (slider).
- Cell popover for editing.
- Lock & re-solve workflow.
- Diff view.

**Deliverable**: full feature parity with v1 on the roster review screen.

### Phase 7 — Views & polish (2–3 days)

- Calendar view (FullCalendar) for blocks AND for roster review.
- Station × date view.
- Per-doctor calendar drawer.
- Keyboard shortcuts.
- Mobile layout pass.

**Deliverable**: v2 is demonstrably nicer than v1.

### Phase 8 — Export (1 day)

- JSON / CSV / HTML / ICS downloads.
- Print preview.
- Per-doctor email mailto: links.
- Share-via-URL.

**Deliverable**: publishing workflow complete.

### Phase 9 — Docs & release (0.5 day)

- Update `docs/CHANGELOG.md` with v2 entries.
- Update `docs/FEATURES.md` with any v2-specific deltas.
- README on the `react-ui` branch points at the new Space.

**Total**: ≈ 15–20 days of focused work for one engineer.

---

## 11. Migration notes — what to copy from `main`

From the current `main` branch, copy these verbatim:

- `scheduler/` (entire directory).
- `tests/test_smoke.py`, `tests/test_h11.py`, `tests/test_stress.py`.
- `docs/CONSTRAINTS.md`, `docs/FEATURES.md`, `docs/CHANGELOG.md`,
  `docs/CONTEXT.md`, `docs/plots/`.
- `configs/default.yaml`.
- `.gitignore`, `.hf_access_token` (if continuing to use token-based push —
  keep in `.gitignore`).

**Delete / replace:**

- `app.py` — replaced by `api/main.py`.
- `requirements.txt` — swap `streamlit` for `fastapi`/`uvicorn`/etc.
- `Dockerfile` — replaced by the multi-stage version in §8.3.

**Things to validate before deploy:**

- Every `scheduler/` public function still tested by `pytest tests/` after
  the FastAPI wrapper is added.
- The YAML round-trip test still passes (`dump_state` → `load_state` →
  `dump_state` should be idempotent on a canonical sample).
- The solve-streaming contract produces the same sequence of events whether
  invoked from `api/routes/solve.py` or the direct `scheduler.model.solve`.

---

## 12. Open questions for the user

The forking agent should pause and ask these before finalising:

1. **HF Space name** — e.g. `doctor_roster_v2`, `doctor_roster_modern`, or
   something else?
2. **Branch name** — `react-ui`, `v2-ui`, `modern-ui`, or `v2`?
3. **Dark mode default** — on or off?
4. **Calendar library licence** — FullCalendar's Standard edition is
   GPL/MIT-ish; confirm that's acceptable, or switch to `react-big-calendar`.
5. **Session persistence** — is `localStorage` + manual YAML
   download/upload enough, or do we want the backend to write to a mounted
   volume? (HF Spaces volumes cost extra.)
6. **Authentication** — HF Space access gating is usually via HF account
   sharing. Do you want an additional app-level password, or keep it as
   "whoever reaches the Space can use it"?

Default answers if the user doesn't answer: `doctor_roster_v2`, `react-ui`,
dark mode off, FullCalendar standard, localStorage-only, no app-level auth.

---

## 13. Success criteria

The v2 is "done" when a roster coordinator can:

- Open the Space on a desktop browser, load a saved YAML, solve a 30-
  doctor × 28-day roster, drag one cell to move an assignment, re-solve
  around it, and export a PDF — **without ever waiting for the page to
  reload**.
- Open the same Space on their phone at night and check who is on call
  for the next 3 days in under 10 seconds.
- Produce next month's roster by cloning last month's YAML, uploading
  last month's JSON for `prev_workload`, editing the dates and any new
  leave, and solving — in under 5 minutes of active work.

---

## 14. Final note

The v1 Streamlit app is proof that the *solver and constraint model* work.
v2 is a UI rewrite, not a product pivot. If anything in this plan tempts
you to touch `scheduler/`, push back on the user first — nine out of ten
times the right answer is to work around it in the UI or API layer.
