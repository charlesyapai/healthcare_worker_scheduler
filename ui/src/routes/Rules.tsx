import { PlaceholderRoute } from "./PlaceholderRoute";

export function Rules() {
  return (
    <PlaceholderRoute
      title="Department rules"
      phase="Phase 4"
      description="Set once per department: tiers, sub-specs, stations, rules, hours, fairness weights, solver priorities."
      todo={[
        "Tiers + sub-specs editors",
        "Stations as a card grid with mini-diagram",
        "Rules toggles (segmented control)",
        "Hours per shift table with live bar chart",
        "Workload + solver priority weights with live preview",
      ]}
    />
  );
}
