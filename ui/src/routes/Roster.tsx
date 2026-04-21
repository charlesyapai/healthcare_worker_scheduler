import { PlaceholderRoute } from "./PlaceholderRoute";

export function Roster() {
  return (
    <PlaceholderRoute
      title="Roster"
      phase="Phase 6"
      description="Review, edit, and re-solve. Three view modes (calendar, heatmap, station-by-date)."
      todo={[
        "Doctor × date heatmap grid (TanStack Table)",
        "Click-cell popover with eligible-doctor swap",
        "Snapshot picker (slider across intermediate solutions)",
        "Workload headline + drawer with per-doctor breakdown",
        "Lock-and-re-solve workflow",
        "Diff view against another snapshot",
      ]}
    />
  );
}
