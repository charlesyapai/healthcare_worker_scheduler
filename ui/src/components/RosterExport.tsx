/**
 * Inline export controls for the Roster page.
 *
 * The 2026-04-25 IA pass dropped the standalone /export route — the
 * roster grid IS the preview, so a separate page that re-rendered the
 * same grid was duplication. This component packages the action
 * buttons (download formats, print, share, mailto) into three compact
 * cards that the Roster page renders below the heatmap.
 *
 * Uses the currently-selected snapshot from `useSolveStore` so what
 * the user exports always matches what they're looking at.
 */

import { format } from "date-fns";
import {
  Calendar,
  Clipboard,
  FileJson,
  FileSpreadsheet,
  FileText,
  Link as LinkIcon,
  Mail,
  Printer,
  Send,
  Share2,
} from "lucide-react";
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
import type { AssignmentRow } from "@/store/solve";
import { useSolveStore } from "@/store/solve";

export function RosterExport() {
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
  const nDays = data?.horizon?.n_days ?? 0;

  const noResult = rows.length === 0 || !result;

  const downloadJson = () => {
    if (!result) return;
    const payload = {
      meta: {
        status: result.status,
        start_date: startDate,
        n_days: nDays,
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
    downloadBlob(buildIcs(rows), `roster_${today()}.ics`, "text/calendar");
  };

  const openPrintPreview = () => {
    const html = buildPrintableHtml({
      title: `Roster ${startDate ?? ""}`.trim(),
      rows,
      doctors: doctors.map((d) => d.name),
      startDate,
      nDays,
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

  if (noResult) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Export this roster</CardTitle>
        <CardDescription className="text-xs">
          {rows.length} assignment{rows.length === 1 ? "" : "s"} ·{" "}
          {doctors.length} people · {nDays}-day horizon
          {startDate ? ` from ${format(new Date(startDate), "d MMM")}` : ""}.
          The grid above is the preview — pick a format below to send it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-3">
          <ActionCard
            icon={FileText}
            title="Files"
            description="Open directly or attach to an email."
          >
            <Button size="sm" variant="secondary" onClick={downloadJson}>
              <FileJson className="h-4 w-4" />
              JSON
            </Button>
            <Button size="sm" variant="secondary" onClick={downloadCsv}>
              <FileSpreadsheet className="h-4 w-4" />
              CSV
            </Button>
            <Button size="sm" variant="secondary" onClick={downloadIcs}>
              <Calendar className="h-4 w-4" />
              Calendar (.ics)
            </Button>
          </ActionCard>

          <ActionCard
            icon={Printer}
            title="Print & share"
            description="Hand a copy to a colleague or the admin team."
          >
            <Button size="sm" variant="secondary" onClick={openPrintPreview}>
              <Printer className="h-4 w-4" />
              Print preview
            </Button>
            <Button size="sm" variant="ghost" onClick={copyYaml}>
              <Clipboard className="h-4 w-4" />
              Copy YAML
            </Button>
            <Button size="sm" variant="ghost" onClick={() => shareViaUrl(data)}>
              <LinkIcon className="h-4 w-4" />
              Copy share link
            </Button>
          </ActionCard>

          <ActionCard
            icon={Share2}
            title="Distribute"
            description="Per-doctor mailto: links with pre-filled schedule."
          >
            <DoctorMailtoList
              rows={rows}
              doctors={doctors.map((d) => d.name)}
              startDate={startDate}
            />
          </ActionCard>
        </div>
      </CardContent>
    </Card>
  );
}

function ActionCard({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/50 p-3 dark:border-slate-800 dark:bg-slate-900/40">
      <div className="mb-1 flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-300" />
        <span className="text-sm font-semibold">{title}</span>
      </div>
      <p className="mb-2 text-[11px] text-slate-500 dark:text-slate-400">
        {description}
      </p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function DoctorMailtoList({
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
  const populated = doctors.filter((n) => (byDoctor.get(n) ?? []).length > 0);
  if (populated.length === 0) {
    return (
      <p className="text-xs text-slate-500 dark:text-slate-400">
        No per-doctor rows to distribute.
      </p>
    );
  }
  return (
    <div className="grid max-h-48 w-full gap-1 overflow-y-auto">
      {populated.map((name) => {
        const list = byDoctor.get(name)!;
        const body = buildMailBody(name, list, startDate);
        const subject = encodeURIComponent(
          `Your roster for ${startDate ?? "upcoming period"}`,
        );
        const href = `mailto:?subject=${subject}&body=${encodeURIComponent(body)}`;
        return (
          <a
            key={name}
            href={href}
            className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] hover:border-indigo-300 hover:bg-indigo-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-700 dark:hover:bg-indigo-950"
          >
            <span className="truncate font-medium">{name}</span>
            <span className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
              {list.length}
              <Mail className="h-3 w-3" />
              <Send className="h-3 w-3" />
            </span>
          </a>
        );
      })}
    </div>
  );
}

// ----------------------------------------------------------------- helpers
// (Same wire-format generators as the old standalone Export page; kept
// alongside the component so a single import gives the caller every
// download / print / share affordance.)

function buildMailBody(
  name: string,
  rows: AssignmentRow[],
  startDate: string | null,
): string {
  const sorted = [...rows].sort(
    (a, b) => a.date.localeCompare(b.date) || a.role.localeCompare(b.role),
  );
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
    "PRODID:-//Charles' Healthcare Roster Scheduler//EN",
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
  return s
    .replace(/\\/g, "\\\\")
    .replace(/,/g, "\\,")
    .replace(/;/g, "\\;")
    .replace(/\n/g, "\\n");
}

function buildPrintableHtml(args: {
  title: string;
  rows: AssignmentRow[];
  doctors: string[];
  startDate: string | null;
  nDays: number;
}): string {
  const { title, rows, doctors, startDate, nDays } = args;

  // Chunk the horizon into 7-day "weeks" starting from `startDate`.
  const weeks: string[][] = [];
  if (startDate && nDays > 0) {
    const start = new Date(`${startDate}T00:00`);
    let cursor: string[] = [];
    for (let i = 0; i < nDays; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      cursor.push(d.toISOString().slice(0, 10));
      if (cursor.length === 7) {
        weeks.push(cursor);
        cursor = [];
      }
    }
    if (cursor.length) weeks.push(cursor);
  }

  const key = (doctor: string, date: string) => `${doctor}|${date}`;
  const cell = new Map<string, string[]>();
  for (const r of rows) {
    const k = key(r.doctor, r.date);
    const list = cell.get(k) ?? [];
    list.push(compactRole(r.role));
    cell.set(k, list);
  }

  const weekBlocks = weeks
    .map((days, wIdx) => buildWeekBlock({ days, doctors, cell, key, wIdx }))
    .join("\n");

  return `<!doctype html>
<html><head>
<meta charset="UTF-8" />
<title>${escapeHtml(title)}</title>
<style>
  :root { color-scheme: light; }
  body { font: 11px ui-sans-serif, system-ui, sans-serif; margin: 16px; color: #0f172a; background: #ffffff; }
  h1 { font-size: 16px; margin: 0 0 12px; }
  .week { margin: 0 0 18px; break-inside: avoid; page-break-inside: avoid; }
  .week-head { display: flex; align-items: baseline; justify-content: space-between; margin: 0 0 4px; font-size: 11px; font-weight: 600; color: #334155; }
  .week-head .range { font-weight: 400; color: #64748b; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  col.doctor { width: 22%; }
  col.day { width: 11.14%; }
  th, td { border: 1px solid #cbd5e1; padding: 3px 4px; font-size: 10px; text-align: center; vertical-align: middle; word-break: break-word; }
  th { background: #f1f5f9; }
  th.weekend { background: #fef3c7; color: #92400e; }
  td.weekend { background: #fffbeb; }
  tr > th:first-child, tr > td:first-child { text-align: left; background: #f8fafc; font-weight: 500; }
  td:empty::after { content: "·"; color: #cbd5e1; }
  @media print { body { margin: 8mm; } h1 { font-size: 13px; margin-bottom: 8px; } .week { margin-bottom: 10px; } }
</style>
</head><body>
<h1>${escapeHtml(title)}</h1>
${weekBlocks}
<script>window.onload = () => setTimeout(() => window.print(), 250);</script>
</body></html>`;
}

function buildWeekBlock(args: {
  days: string[];
  doctors: string[];
  cell: Map<string, string[]>;
  key: (doctor: string, date: string) => string;
  wIdx: number;
}): string {
  const { days, doctors, cell, key, wIdx } = args;
  const first = days[0];
  const last = days[days.length - 1];
  const rangeLabel = formatDayRange(first, last);

  const PAD = 7;
  const paddedDays = days.slice();
  while (paddedDays.length < PAD) paddedDays.push("");

  const colDefs =
    '<col class="doctor" />' +
    paddedDays.map(() => '<col class="day" />').join("");

  const head = paddedDays
    .map((iso) => {
      if (!iso) return "<th></th>";
      const d = new Date(`${iso}T00:00`);
      const dow = d.getDay();
      const we = dow === 0 || dow === 6;
      const weekdayShort = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dow];
      const label = `${weekdayShort}<br>${iso.slice(5)}`;
      return `<th class="${we ? "weekend" : ""}">${label}</th>`;
    })
    .join("");

  const body = doctors
    .map((name) => {
      const cells = paddedDays
        .map((iso) => {
          if (!iso) return "<td></td>";
          const d = new Date(`${iso}T00:00`);
          const dow = d.getDay();
          const we = dow === 0 || dow === 6;
          const cs = (cell.get(key(name, iso)) ?? []).join(" / ");
          return `<td class="${we ? "weekend" : ""}">${escapeHtml(cs)}</td>`;
        })
        .join("");
      return `<tr><td>${escapeHtml(name)}</td>${cells}</tr>`;
    })
    .join("");

  return `<section class="week">
  <div class="week-head">
    <span>Week ${wIdx + 1}</span>
    <span class="range">${rangeLabel}</span>
  </div>
  <table>
    <colgroup>${colDefs}</colgroup>
    <thead><tr><th>Doctor</th>${head}</tr></thead>
    <tbody>${body}</tbody>
  </table>
</section>`;
}

function formatDayRange(firstIso: string, lastIso: string): string {
  if (!firstIso || !lastIso) return "";
  const a = new Date(`${firstIso}T00:00`);
  const b = new Date(`${lastIso}T00:00`);
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" };
  const sameMonth =
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
  const aTxt = a.toLocaleDateString("en-GB", sameMonth ? { day: "numeric" } : opts);
  const bTxt = b.toLocaleDateString("en-GB", {
    ...opts,
    year: a.getFullYear() !== b.getFullYear() ? "numeric" : undefined,
  });
  return `${aTxt} – ${bTxt}`;
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
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c]!,
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
