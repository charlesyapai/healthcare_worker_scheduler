import { format } from "date-fns";

import { type DoctorEntry } from "@/api/hooks";
import {
  type CellContent,
  type Horizon,
  buildCellMap,
  cellColorClass,
  cellKind,
  cellLabel,
  formatDay,
  horizonDates,
  isWeekendOrHoliday,
} from "@/lib/roster";
import { cn } from "@/lib/utils";
import type { AssignmentRow } from "@/store/solve";

interface Props {
  doctors: DoctorEntry[];
  assignments: AssignmentRow[];
  blocks: Array<{ doctor: string; date: string; end_date?: string | null; type: string }>;
  horizon: Horizon;
  onCellClick?: (ctx: { doctor: string; date: string; content: CellContent }) => void;
  highlightKeys?: Set<string>;
}

export function RosterHeatmap({
  doctors,
  assignments,
  blocks,
  horizon,
  onCellClick,
  highlightKeys,
}: Props) {
  const dates = horizonDates(horizon);
  const holidays = horizon.public_holidays ?? [];
  const doctorNames = doctors.map((d) => d.name);
  const cellMap = buildCellMap(assignments, blocks, dates, doctorNames);

  if (dates.length === 0 || doctorNames.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
        Configure doctors + start date to see the roster grid.
      </div>
    );
  }

  return (
    <div className="overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
      <table className="min-w-full border-collapse text-[11px]">
        <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-900">
          <tr>
            <th className="sticky left-0 z-20 min-w-[8rem] border-b border-r border-slate-200 bg-slate-50 px-2 py-1.5 text-left font-semibold dark:border-slate-800 dark:bg-slate-900">
              Doctor
            </th>
            {dates.map((d) => {
              const we = isWeekendOrHoliday(d, holidays);
              return (
                <th
                  key={format(d, "yyyy-MM-dd")}
                  className={cn(
                    "border-b border-r border-slate-200 px-1.5 py-1 text-center font-medium dark:border-slate-800",
                    we && "bg-slate-100 dark:bg-slate-800/60",
                  )}
                >
                  <div className="whitespace-nowrap">{formatDay(d)}</div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {doctors.map((d, rowIdx) => (
            <tr key={d.name} className={cn(rowIdx % 2 ? "bg-slate-50/50 dark:bg-slate-900/40" : "")}>
              <td className="sticky left-0 z-10 min-w-[8rem] border-b border-r border-slate-200 bg-inherit px-2 py-1 font-medium dark:border-slate-800">
                <span>{d.name}</span>
                <span className="ml-1 text-[10px] uppercase text-slate-400">
                  {d.tier[0]}
                </span>
              </td>
              {dates.map((dt) => {
                const iso = format(dt, "yyyy-MM-dd");
                const content = cellMap.get(`${d.name}|${iso}`) ?? {};
                const we = isWeekendOrHoliday(dt, holidays);
                const kind = cellKind(content, !we);
                const label = cellLabel(content);
                const key = `${d.name}|${iso}`;
                const highlight = highlightKeys?.has(key);
                return (
                  <td
                    key={iso}
                    className={cn(
                      "h-8 min-w-[4.5rem] cursor-pointer border-b border-r border-slate-200 px-1 text-center align-middle font-mono text-[10px] leading-tight transition-colors dark:border-slate-800",
                      cellColorClass(kind),
                      highlight && "outline outline-2 outline-indigo-500",
                    )}
                    onClick={() => onCellClick?.({ doctor: d.name, date: iso, content })}
                    title={label || (we ? "" : "idle")}
                  >
                    {label}
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
