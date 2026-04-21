import { PlaceholderRoute } from "./PlaceholderRoute";

export function Setup() {
  return (
    <PlaceholderRoute
      title="Setup"
      phase="Phase 3"
      description="Per-period inputs: dates, doctors, leave and blocks, manual overrides."
      todo={[
        "Inline date-range picker + public-holiday chips",
        "Spreadsheet-style doctors table with keyboard nav and clipboard paste",
        "Blocks editor (table view; calendar view arrives in Phase 7)",
        "Manual overrides table with filters",
        "CSV bulk-paste drawer",
        "Auto-save via debounced PATCH",
      ]}
    />
  );
}
