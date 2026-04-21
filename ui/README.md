# ui/

React SPA source for the v2 fork. Vite + React 18 + TypeScript + Tailwind
CSS 4 + TanStack Query + Zustand + React Router. In production the built
bundle is copied into `api/static/` by the multi-stage Dockerfile and
served by FastAPI on port 7860.

## Scripts

```bash
pnpm install          # first-time setup
pnpm dev              # Vite dev server on :5173, proxies /api to :7860
pnpm build            # typecheck + Vite production bundle → ui/dist/
pnpm gen:types        # regenerate src/api/types.ts from src/api/openapi.json
pnpm typecheck        # tsc --noEmit
```

## Regenerate the OpenAPI spec after a backend change

From the repo root:

```bash
python scripts/dump_openapi.py > ui/src/api/openapi.json
cd ui && pnpm gen:types
```

Both `openapi.json` and `types.ts` are committed so Docker builds don't
need a running API to typecheck.

## Layout

See [`docs/NEW_UI_PLAN.md`](../docs/NEW_UI_PLAN.md) §9 for the target
directory layout and §8 for dependency choices.
