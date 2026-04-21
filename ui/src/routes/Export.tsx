import { PlaceholderRoute } from "./PlaceholderRoute";

export function Export() {
  return (
    <PlaceholderRoute
      title="Export"
      phase="Phase 8"
      description="Download, print, share."
      todo={[
        "JSON / CSV / HTML / ICS downloads",
        "Print preview matching the PDF layout",
        "Per-doctor mailto: preview links",
        "Share-via-URL (Base64-compressed state)",
      ]}
    />
  );
}
