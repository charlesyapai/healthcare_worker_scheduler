import { addDays, format, parseISO } from "date-fns";
import {
  Calendar,
  Clipboard,
  Eye,
  FileJson,
  FileSpreadsheet,
  FileText,
  Link as LinkIcon,
  Mail,
  Printer,
  Send,
  Share2,
} from "lucide-react";
import { useMemo, useState } from "react";
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
import { cn } from "@/lib/utils";
import { useSolveStore } from "@/store/solve";
import type { AssignmentRow } from "@/store/solve";

export function Export() {
  const { data } = useSessionState();
  const { result, events, selectedSnapshot } = useSolveStore();
  const yaml = useYamlExport();
  const [view, setView] = useState<"grid" | "list">("grid");

  const rows = useMemo<AssignmentRow[]>(() => {
    if (!result) return [];
    if (selectedSnapshot === "final") return result.assignments ?? [];
    return events[selectedSnapshot]?.assignments ?? result.assignments ?? [];
  }, [result, events, selectedSnapshot]);

  const doctors = data?.doctors ?? [];
  const startDate = data?.horizon?.start_date ?? null;
  const nDays = data?.horizon?.n_days ?? 0;

  const dates = useMemo<Date[]>(() => {
    if (!startDate || !nDays) return [];
    const start = parseISO(startDate);
    return Array.from({ length: nDays }, (_, i) => addDays(start, i));
  }, [startDate, nDays]);

  const byCell = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const r of rows) {
      const k = `${r.doctor}|${r.date}`;
      const list = m.get(k) ?? [];
      list.push(compactRole(r.role));
      m.set(k, list);
    }
    return m;
  }, [rows]);

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

  if (noResult) {
    return (
      <div className="mx-auto max-w-5xl space-y-4">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Export</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Download, print, share — based on the currently-selected snapshot.
          </p>
        </header>
        <Card>
          <CardContent className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
            No solved roster yet. Head to{" "}
            <strong className="text-slate-700 dark:text-slate-200">Solve</strong>{" "}
            to produce one.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Export</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {rows.length} assignment{rows.length === 1 ? "" : "s"} ·{" "}
            {doctors.length} people · {nDays}-day horizon
            {startDate ? ` from ${format(parseISO(startDate), "d MMM")}` : ""}.
          </p>
        </div>
        <div
          className="inline-flex overflow-hidden rounded-md border border-slate-200 dark:border-slate-800"
          role="tablist"
          aria-label="View mode"
        >
          <button
            type="button"
            onClick={() => setView("grid")}
            className={cn(
              "px-3 py-1 text-xs font-medium",
              view === "grid"
                ? "bg-indigo-600 text-white"
                : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
            )}
          >
            Grid
          </button>
          <button
            type="button"
            onClick={() => setView("list")}
            className={cn(
              "px-3 py-1 text-xs font-medium",
              view === "list"
                ? "bg-indigo-600 text-white"
                : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
            )}
          >
            List
          </button>
        </div>
      </header>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Eye className="h-4 w-4 text-slate-500" />
            <CardTitle className="text-sm">Preview</CardTitle>
          </div>
          <CardDescription className="text-xs">
            What you'll see in the print-out and in downloads. Switch view to
            check either layout before exporting.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {view === "grid" ? (
            <GridPreview
              doctors={doctors.map((d) => d.name)}
              dates={dates}
              byCell={byCell}
            />
          ) : (
            <ListPreview rows={rows} />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-3">
        <ActionCard
          icon={FileText}
          title="Files"
          description="One per format. Open directly or attach to an email."
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
    </div>
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
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <CardTitle className="text-sm">{title}</CardTitle>
        </div>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">{children}</CardContent>
    </Card>
  );
}

function GridPreview({
  doctors,
  dates,
  byCell,
}: {
  doctors: string[];
  dates: Date[];
  byCell: Map<string, string[]>;
}) {
  if (dates.length === 0 || doctors.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-slate-500 dark:text-slate-400">
        Set a horizon and add doctors to see the grid.
      </p>
    );
  }
  const monthTickIso = new Set<string>();
  for (const d of dates) {
    if (d.getDate() === 1) monthTickIso.add(format(d, "yyyy-MM-dd"));
  }
  return (
    <div className="max-h-[60vh] overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
      <table className="min-w-full text-[11px]">
        <thead>
          <tr className="text-slate-500 dark:text-slate-400">
            <th
              className="sticky left-0 top-0 z-20 border-b border-slate-200 bg-slate-50 px-2 py-1 text-left font-medium dark:border-slate-800 dark:bg-slate-900"
              style={{ minWidth: 140 }}
            >
              Doctor
            </th>
            {dates.map((d) => {
              const iso = format(d, "yyyy-MM-dd");
              const isWeekend = d.getDay() === 0 || d.getDay() === 6;
              return (
                <th
                  key={iso}
                  className={cn(
                    "sticky top-0 z-10 border-b border-slate-200 px-0.5 py-1 text-center font-mono dark:border-slate-800",
                    isWeekend
                      ? "bg-slate-100 text-rose-500 dark:bg-slate-900 dark:text-rose-400/70"
                      : "bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-300",
                    monthTickIso.has(iso) &&
                      "border-l border-l-slate-300 dark:border-l-slate-700",
                  )}
                  style={{ minWidth: 28 }}
                  title={format(d, "EEE d MMM yyyy")}
                >
                  <div>{format(d, "d")}</div>
                  <div className="text-[9px] opacity-70">
                    {format(d, "EEEEE")}
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {doctors.map((doc, rowIdx) => (
            <tr key={doc}>
              <td
                className={cn(
                  "sticky left-0 z-10 border-b border-slate-100 px-2 py-1 font-medium dark:border-slate-800",
                  rowIdx % 2 === 0
                    ? "bg-white dark:bg-slate-950"
                    : "bg-slate-50 dark:bg-slate-900/50",
                )}
                style={{ minWidth: 140 }}
              >
                {doc}
              </td>
              {dates.map((d) => {
                const iso = format(d, "yyyy-MM-dd");
                const cells = byCell.get(`${doc}|${iso}`) ?? [];
                const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                return (
                  <td
                    key={iso}
                    className={cn(
                      "border-b border-slate-100 px-0.5 py-1 text-center font-mono dark:border-slate-800",
                      isWeekend && "bg-slate-50/60 dark:bg-slate-900/30",
                      monthTickIso.has(iso) &&
                        "border-l border-l-slate-200 dark:border-l-slate-800",
                    )}
                    style={{ minWidth: 28 }}
                  >
                    {cells.length > 0 ? (
                      <span className="inline-block rounded bg-indigo-50 px-1 text-[10px] text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">
                        {cells.join(" ")}
                      </span>
                    ) : (
                      <span className="text-slate-300 dark:text-slate-700">
                        ·
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ListPreview({ rows }: { rows: AssignmentRow[] }) {
  const sorted = [...rows].sort(
    (a, b) =>
      a.date.localeCompare(b.date) ||
      a.doctor.localeCompare(b.doctor) ||
      a.role.localeCompare(b.role),
  );
  return (
    <div className="max-h-[60vh] overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
      <table className="min-w-full text-xs">
        <thead className="sticky top-0 bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:bg-slate-900 dark:text-slate-400">
          <tr>
            <th className="px-3 py-1.5">Date</th>
            <th className="px-3 py-1.5">Doctor</th>
            <th className="px-3 py-1.5">Role</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {sorted.map((r, i) => (
            <tr
              key={i}
              className="hover:bg-slate-50 dark:hover:bg-slate-900/50"
            >
              <td className="px-3 py-1 font-mono">{r.date}</td>
              <td className="px-3 py-1">{r.doctor}</td>
              <td className="px-3 py-1 font-mono text-slate-600 dark:text-slate-400">
                {r.role}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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

  const head = dates.map((d) => `<th>${d.slice(5)}</th>`).join("");
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
