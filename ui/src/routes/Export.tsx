import { format } from "date-fns";
import { Calendar, Clipboard, FileJson, FileSpreadsheet, FileText, Mail, Printer } from "lucide-react";
import { useMemo } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useSessionState, useYamlExport } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useSolveStore } from "@/store/solve";
import type { AssignmentRow } from "@/store/solve";

export function Export() {
  const { data } = useSessionState();
  const { result, events, selectedSnapshot } = useSolveStore();
  const yaml = useYamlExport();

  const rows = useMemo<AssignmentRow[]>(() => {
    if (!result) return [];
    if (selectedSnapshot === "final") return result.assignments ?? [];
    return events[selectedSnapshot]?.assignments ?? result.assignments ?? [];
  }, [result, events, selectedSnapshot]);

  const doctors = data?.doctors ?? [];
  const startDate = data?.horizon?.start_date ?? null;

  const noResult = rows.length === 0 || !result;

  const downloadJson = () => {
    if (!result) return;
    const payload = {
      meta: {
        status: result.status,
        start_date: startDate,
        n_days: data?.horizon?.n_days ?? 0,
        wall_time: result.wall_time_s,
        objective: result.objective,
        best_bound: result.best_bound,
        first_feasible: result.first_feasible_s,
        penalty_components: result.penalty_components,
      },
      assignments: rows,
    };
    downloadBlob(
      JSON.stringify(payload, null, 2),
      `roster_${today()}.json`,
      "application/json",
    );
  };

  const downloadCsv = () => {
    const header = "doctor,date,role\n";
    const body = rows.map((r) => `${r.doctor},${r.date},${r.role}`).join("\n");
    downloadBlob(header + body, `roster_${today()}.csv`, "text/csv");
  };

  const downloadIcs = () => {
    const ics = buildIcs(rows);
    downloadBlob(ics, `roster_${today()}.ics`, "text/calendar");
  };

  const openPrintPreview = () => {
    const html = buildPrintableHtml({
      title: `Roster ${startDate ?? ""}`.trim(),
      rows,
      doctors: doctors.map((d) => d.name),
      startDate,
      nDays: data?.horizon?.n_days ?? 0,
    });
    const w = window.open("", "_blank", "width=1024,height=800");
    if (!w) {
      toast.error("Pop-up blocked — allow pop-ups to open print preview.");
      return;
    }
    w.document.open();
    w.document.write(html);
    w.document.close();
  };

  const copyYaml = async () => {
    try {
      const out = await yaml.mutateAsync();
      await navigator.clipboard.writeText(out.yaml);
      toast.success("YAML copied to clipboard");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to copy YAML");
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Export</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Download, print, share. Operates on the currently-selected snapshot.
        </p>
      </header>

      {noResult ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
            No solved roster yet. Head to <strong className="text-slate-700 dark:text-slate-200">Solve</strong> to produce one.
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Download</CardTitle>
              <CardDescription>
                {rows.length} assignment{rows.length === 1 ? "" : "s"} across {data?.horizon?.n_days ?? 0} days.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={downloadJson}>
                <FileJson className="h-4 w-4" />
                JSON
              </Button>
              <Button variant="secondary" size="sm" onClick={downloadCsv}>
                <FileSpreadsheet className="h-4 w-4" />
                CSV
              </Button>
              <Button variant="secondary" size="sm" onClick={downloadIcs}>
                <Calendar className="h-4 w-4" />
                ICS
              </Button>
              <Button variant="secondary" size="sm" onClick={openPrintPreview}>
                <Printer className="h-4 w-4" />
                Print preview
              </Button>
              <Button variant="ghost" size="sm" onClick={copyYaml}>
                <Clipboard className="h-4 w-4" />
                Copy YAML
              </Button>
              <Button variant="ghost" size="sm" onClick={() => shareViaUrl(data)}>
                <FileText className="h-4 w-4" />
                Share link
              </Button>
            </CardContent>
          </Card>

          <DoctorMailtos rows={rows} doctors={doctors.map((d) => d.name)} startDate={startDate} />
        </>
      )}
    </div>
  );
}

function DoctorMailtos({
  rows,
  doctors,
  startDate,
}: {
  rows: AssignmentRow[];
  doctors: string[];
  startDate: string | null;
}) {
  const byDoctor = new Map<string, AssignmentRow[]>();
  for (const r of rows) {
    if (!byDoctor.has(r.doctor)) byDoctor.set(r.doctor, []);
    byDoctor.get(r.doctor)!.push(r);
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Per-doctor email previews</CardTitle>
        <CardDescription>
          Click a doctor to open a mailto: with their schedule in the body.
          No SMTP — copy/paste into your mail client.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {doctors.map((name) => {
            const list = byDoctor.get(name) ?? [];
            if (list.length === 0) return null;
            const body = buildMailBody(name, list, startDate);
            const subject = encodeURIComponent(`Your roster for ${startDate ?? "upcoming period"}`);
            const href = `mailto:?subject=${subject}&body=${encodeURIComponent(body)}`;
            return (
              <a
                key={name}
                href={href}
                className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-sm hover:border-indigo-300 hover:bg-indigo-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-700 dark:hover:bg-indigo-950"
              >
                <span className="font-medium">{name}</span>
                <span className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                  {list.length} row{list.length === 1 ? "" : "s"}
                  <Mail className="h-3.5 w-3.5" />
                </span>
              </a>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function buildMailBody(name: string, rows: AssignmentRow[], startDate: string | null): string {
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date) || a.role.localeCompare(b.role));
  const lines = sorted.map((r) => `  ${r.date}  ${r.role}`);
  return [
    `Hi ${name},`,
    "",
    `Here is your roster${startDate ? ` starting ${startDate}` : ""}:`,
    "",
    ...lines,
    "",
    "Please let us know if there are any issues.",
    "",
  ].join("\n");
}

function buildIcs(rows: AssignmentRow[]): string {
  const stamp = format(new Date(), "yyyyMMdd'T'HHmmss'Z'");
  const out = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Healthcare Roster Scheduler v2//EN",
    "CALSCALE:GREGORIAN",
  ];
  for (const r of rows) {
    const dt = r.date.replace(/-/g, "");
    out.push(
      "BEGIN:VEVENT",
      `UID:${r.doctor}-${r.date}-${r.role}@roster.local`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${dt}`,
      `DTEND;VALUE=DATE:${dt}`,
      `SUMMARY:${escapeIcs(`${r.role} — ${r.doctor}`)}`,
      `DESCRIPTION:${escapeIcs(`${r.role} assigned to ${r.doctor}`)}`,
      "TRANSP:OPAQUE",
      "END:VEVENT",
    );
  }
  out.push("END:VCALENDAR");
  return out.join("\r\n");
}

function escapeIcs(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/,/g, "\\,").replace(/;/g, "\\;").replace(/\n/g, "\\n");
}

function buildPrintableHtml(args: {
  title: string;
  rows: AssignmentRow[];
  doctors: string[];
  startDate: string | null;
  nDays: number;
}): string {
  const { title, rows, doctors, startDate, nDays } = args;
  const dates: string[] = [];
  if (startDate && nDays > 0) {
    const start = new Date(startDate);
    for (let i = 0; i < nDays; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      dates.push(d.toISOString().slice(0, 10));
    }
  }

  const key = (doctor: string, date: string) => `${doctor}|${date}`;
  const cell = new Map<string, string[]>();
  for (const r of rows) {
    const k = key(r.doctor, r.date);
    const list = cell.get(k) ?? [];
    list.push(compactRole(r.role));
    cell.set(k, list);
  }

  const head = dates
    .map((d) => `<th>${d.slice(5)}</th>`)
    .join("");
  const body = doctors
    .map((name) => {
      const cells = dates
        .map((d) => {
          const cs = (cell.get(key(name, d)) ?? []).join(" / ");
          return `<td>${cs}</td>`;
        })
        .join("");
      return `<tr><th>${escapeHtml(name)}</th>${cells}</tr>`;
    })
    .join("");

  return `<!doctype html>
<html><head>
<meta charset="UTF-8" />
<title>${escapeHtml(title)}</title>
<style>
  body { font: 11px ui-sans-serif, system-ui, sans-serif; margin: 16px; color: #0f172a; }
  h1 { font-size: 16px; margin: 0 0 12px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #cbd5e1; padding: 3px 5px; text-align: center; font-size: 10px; }
  th { background: #f1f5f9; position: sticky; top: 0; }
  tr > th:first-child { text-align: left; background: #f8fafc; min-width: 130px; }
  @media print { body { margin: 8mm; } h1 { font-size: 14px; } }
</style>
</head><body>
<h1>${escapeHtml(title)}</h1>
<table>
<thead><tr><th>Doctor</th>${head}</tr></thead>
<tbody>${body}</tbody>
</table>
<script>window.onload = () => setTimeout(() => window.print(), 250);</script>
</body></html>`;
}

function compactRole(role: string): string {
  if (role === "ONCALL") return "OC";
  if (role === "WEEKEND_EXT") return "EXT";
  if (role === "WEEKEND_CONSULT") return "WC";
  if (role.startsWith("STATION_")) {
    const parts = role.slice(8).split("_");
    const sess = parts.pop();
    return `${sess}:${parts.join("_")}`;
  }
  return role;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

function today(): string {
  return format(new Date(), "yyyy-MM-dd");
}

function downloadBlob(text: string, filename: string, type: string) {
  const blob = new Blob([text], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

async function shareViaUrl(data: unknown) {
  try {
    const json = JSON.stringify({ state: data ?? null });
    // Compress naively via URL-safe base64; acceptable for sharing small configs.
    const b64 = btoa(unescape(encodeURIComponent(json)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
    const url = `${window.location.origin}${window.location.pathname}#share=${b64}`;
    await navigator.clipboard.writeText(url);
    toast.success("Share URL copied to clipboard");
  } catch {
    toast.error("Failed to generate share link");
  }
}
