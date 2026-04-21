# ui/

React SPA source. Populated in **Phase 2 — SPA foundations** with a Vite +
React + TypeScript + Tailwind + shadcn/ui scaffold. The built bundle is
copied into `api/static/` at Docker build time by the multi-stage
`Dockerfile` introduced in Phase 2.

See [`docs/NEW_UI_PLAN.md`](../docs/NEW_UI_PLAN.md) §9 for the target
directory layout and §8 for dependency choices.
