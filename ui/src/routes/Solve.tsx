import { PlaceholderRoute } from "./PlaceholderRoute";

export function Solve() {
  return (
    <PlaceholderRoute
      title="Solve"
      phase="Phase 5"
      description="Run the solver. Stream improving solutions over WebSocket."
      todo={[
        "Solver-settings left rail (time limit, workers, feasibility-only)",
        "Live convergence chart (recharts)",
        "Intermediate-solutions table",
        "Stop button wired to WS {action: stop}",
        "Verdict banner on first feasible",
      ]}
    />
  );
}
