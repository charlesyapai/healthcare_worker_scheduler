import { type WorkloadRow } from "@/lib/roster";
import { cn } from "@/lib/utils";

interface Props {
  rows: WorkloadRow[];
  tierLabels: { junior: string; senior: string; consultant: string };
}

export function WorkloadTable({ rows, tierLabels }: Props) {
  if (rows.length === 0) return null;
  const maxAbsDelta = rows.reduce((m, r) => Math.max(m, Math.abs(r.deltaMedian)), 0);

  return (
    <div className="overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
      <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
        <thead className="sticky top-0 bg-slate-50 text-left font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
          <tr>
            <th className="px-2 py-1.5">Doctor</th>
            <th className="px-2 py-1.5">Tier</th>
            <th className="px-2 py-1.5 text-right">Score</th>
            <th className="px-2 py-1.5 text-right">Δ tier med</th>
            <th className="px-2 py-1.5 text-right">h/wk</th>
            <th className="px-2 py-1.5 text-right">Leave</th>
            <th className="px-2 py-1.5 text-right">Idle</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((r) => {
            const shade = maxAbsDelta > 0 ? Math.abs(r.deltaMedian) / maxAbsDelta : 0;
            const color =
              r.deltaMedian > 0
                ? `rgba(239, 68, 68, ${0.1 + shade * 0.35})`
                : r.deltaMedian < 0
                  ? `rgba(59, 130, 246, ${0.1 + shade * 0.35})`
                  : "transparent";
            return (
              <tr key={r.doctor}>
                <td className="px-2 py-1 font-medium">{r.doctor}</td>
                <td className="px-2 py-1 text-slate-500">
                  {tierLabels[r.tier as keyof typeof tierLabels] ?? r.tier}
                  {r.subspec ? <span className="ml-1 text-[10px]">({r.subspec})</span> : null}
                </td>
                <td className="px-2 py-1 text-right font-mono">{r.score.toFixed(0)}</td>
                <td
                  className={cn(
                    "px-2 py-1 text-right font-mono",
                    r.deltaMedian > 0 && "text-red-700 dark:text-red-300",
                    r.deltaMedian < 0 && "text-blue-700 dark:text-blue-300",
                  )}
                  style={{ backgroundColor: color }}
                >
                  {r.deltaMedian > 0 ? "+" : ""}
                  {r.deltaMedian.toFixed(0)}
                </td>
                <td className="px-2 py-1 text-right font-mono">{r.hoursPerWeek.toFixed(1)}</td>
                <td className="px-2 py-1 text-right font-mono">{r.leaveDays}</td>
                <td
                  className={cn(
                    "px-2 py-1 text-right font-mono",
                    r.daysIdle > 0 && "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-200",
                  )}
                >
                  {r.daysIdle}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
