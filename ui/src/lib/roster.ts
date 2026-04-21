/**
 * Pure helpers for roster visualisation. The server owns the solver; the
 * client re-computes derived views (per-cell roles, workload scores, hours)
 * from assignments + session state.
 */

import { addDays, format, parseISO } from "date-fns";

import type { AssignmentRow } from "@/store/solve";

export interface Horizon {
  start_date: string | null;
  n_days: number;
  public_holidays: string[];
}

export interface CellContent {
  am?: string; // station name
  pm?: string;
  oncall?: boolean;
  ext?: boolean;
  wconsult?: boolean;
  leave?: boolean;
}

export type CellKind =
  | "empty"
  | "station-am"
  | "station-pm"
  | "station-both"
  | "oncall"
  | "weekend"
  | "leave"
  | "idle";

export function cellKind(c: CellContent, isWeekday: boolean): CellKind {
  if (c.leave) return "leave";
  if (c.oncall) return "oncall";
  if (c.ext || c.wconsult) return "weekend";
  if (c.am && c.pm) return "station-both";
  if (c.am) return "station-am";
  if (c.pm) return "station-pm";
  if (isWeekday) return "idle";
  return "empty";
}

export function cellColorClass(kind: CellKind): string {
  switch (kind) {
    case "station-both":
      return "bg-emerald-200 dark:bg-emerald-900/70 text-emerald-900 dark:text-emerald-100";
    case "station-am":
    case "station-pm":
      return "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-900 dark:text-emerald-200";
    case "oncall":
      return "bg-purple-200 dark:bg-purple-900/60 text-purple-900 dark:text-purple-100";
    case "weekend":
      return "bg-teal-200 dark:bg-teal-900/60 text-teal-900 dark:text-teal-100";
    case "leave":
      return "bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300";
    case "idle":
      return "bg-amber-200 dark:bg-amber-900/60 text-amber-900 dark:text-amber-200";
    default:
      return "";
  }
}

export function cellLabel(c: CellContent): string {
  if (c.leave) return "LV";
  const parts: string[] = [];
  if (c.am) parts.push(`AM:${c.am}`);
  if (c.pm) parts.push(`PM:${c.pm}`);
  if (c.oncall) parts.push("OC");
  if (c.ext) parts.push("EXT");
  if (c.wconsult) parts.push("WC");
  return parts.join(" / ");
}

export function horizonDates(h: Horizon): Date[] {
  if (!h.start_date) return [];
  const start = parseISO(h.start_date);
  return Array.from({ length: Math.max(0, h.n_days) }, (_, i) => addDays(start, i));
}

export function formatDay(d: Date): string {
  return format(d, "EEE d MMM");
}

export function isWeekendOrHoliday(d: Date, holidays: string[]): boolean {
  const dow = d.getDay();
  if (dow === 0 || dow === 6) return true;
  const iso = format(d, "yyyy-MM-dd");
  return holidays.includes(iso);
}

interface LeaveBlock {
  doctor: string;
  date: string;
  end_date?: string | null;
  type: string;
}

export function buildCellMap(
  assignments: AssignmentRow[],
  blocks: LeaveBlock[],
  dates: Date[],
  doctors: string[],
): Map<string, CellContent> {
  const key = (doctor: string, isoDay: string) => `${doctor}|${isoDay}`;
  const map = new Map<string, CellContent>();

  for (const doctor of doctors) {
    for (const d of dates) {
      map.set(key(doctor, format(d, "yyyy-MM-dd")), {});
    }
  }

  // Leave first (from blocks)
  for (const b of blocks) {
    if (b.type !== "Leave") continue;
    const start = parseISO(b.date);
    const end = b.end_date ? parseISO(b.end_date) : start;
    for (let ts = start.getTime(); ts <= end.getTime(); ts += 86_400_000) {
      const iso = format(new Date(ts), "yyyy-MM-dd");
      const k = key(b.doctor, iso);
      const existing = map.get(k);
      if (existing) existing.leave = true;
    }
  }

  // Overlay assignments
  for (const row of assignments) {
    const iso = row.date;
    const k = key(row.doctor, iso);
    const c = map.get(k);
    if (!c) continue;
    const role = row.role.toUpperCase();
    if (role.startsWith("STATION_")) {
      const parts = role.slice(8).split("_");
      const sess = parts.pop();
      const stationName = parts.join("_");
      if (sess === "AM") c.am = stationName;
      else if (sess === "PM") c.pm = stationName;
    } else if (role === "ONCALL") {
      c.oncall = true;
    } else if (role === "WEEKEND_EXT" || role === "EXT") {
      c.ext = true;
    } else if (role === "WEEKEND_CONSULT" || role === "WCONSULT") {
      c.wconsult = true;
    }
  }

  return map;
}

export interface WorkloadWeightsLike {
  weekday_session: number;
  weekend_session: number;
  weekday_oncall: number;
  weekend_oncall: number;
  weekend_ext: number;
  weekend_consult: number;
}

export interface HoursLike {
  weekday_am: number;
  weekday_pm: number;
  weekend_am: number;
  weekend_pm: number;
  weekday_oncall: number;
  weekend_oncall: number;
  weekend_ext: number;
  weekend_consult: number;
}

export interface WorkloadRow {
  doctor: string;
  tier: string;
  subspec: string | null;
  score: number;
  prevWorkload: number;
  deltaMedian: number;
  hoursPerWeek: number;
  leaveDays: number;
  daysIdle: number;
}

export function computeWorkload(args: {
  doctors: Array<{
    name: string;
    tier: "junior" | "senior" | "consultant";
    subspec: string | null | undefined;
    prev_workload?: number | null;
  }>;
  assignments: AssignmentRow[];
  blocks: LeaveBlock[];
  horizon: Horizon;
  weights: WorkloadWeightsLike;
  hours: HoursLike;
}): WorkloadRow[] {
  const { doctors, assignments, blocks, horizon, weights, hours } = args;
  const dates = horizonDates(horizon);
  const holidays = horizon.public_holidays ?? [];

  const byDoctor = new Map<string, {
    score: number;
    hours: number;
    leaveDays: number;
    idle: number;
  }>();

  for (const d of doctors) {
    byDoctor.set(d.name, { score: 0, hours: 0, leaveDays: 0, idle: 0 });
  }

  // Count leave days from blocks
  for (const b of blocks) {
    if (b.type !== "Leave") continue;
    const who = byDoctor.get(b.doctor);
    if (!who) continue;
    const start = parseISO(b.date);
    const end = b.end_date ? parseISO(b.end_date) : start;
    for (let ts = start.getTime(); ts <= end.getTime(); ts += 86_400_000) {
      const d = new Date(ts);
      const iso = format(d, "yyyy-MM-dd");
      if (!dates.some((x) => format(x, "yyyy-MM-dd") === iso)) continue;
      who.leaveDays += 1;
    }
  }

  // Score + hours from assignments
  for (const row of assignments) {
    const who = byDoctor.get(row.doctor);
    if (!who) continue;
    const d = parseISO(row.date);
    const we = isWeekendOrHoliday(d, holidays);
    const role = row.role.toUpperCase();
    if (role.startsWith("STATION_")) {
      const sess = role.split("_").pop();
      who.score += we ? weights.weekend_session : weights.weekday_session;
      if (we) who.hours += sess === "AM" ? hours.weekend_am : hours.weekend_pm;
      else who.hours += sess === "AM" ? hours.weekday_am : hours.weekday_pm;
    } else if (role === "ONCALL") {
      who.score += we ? weights.weekend_oncall : weights.weekday_oncall;
      who.hours += we ? hours.weekend_oncall : hours.weekday_oncall;
    } else if (role === "WEEKEND_EXT" || role === "EXT") {
      who.score += weights.weekend_ext;
      who.hours += hours.weekend_ext;
    } else if (role === "WEEKEND_CONSULT" || role === "WCONSULT") {
      who.score += weights.weekend_consult;
      who.hours += hours.weekend_consult;
    }
  }

  // Idle-weekday count: weekdays with no assignment and no leave.
  const cellMap = buildCellMap(
    assignments,
    blocks,
    dates,
    doctors.map((d) => d.name),
  );
  for (const d of doctors) {
    const who = byDoctor.get(d.name)!;
    for (const dt of dates) {
      if (isWeekendOrHoliday(dt, holidays)) continue;
      const iso = format(dt, "yyyy-MM-dd");
      const c = cellMap.get(`${d.name}|${iso}`);
      if (!c) continue;
      if (cellKind(c, true) === "idle") who.idle += 1;
    }
  }

  const weeks = Math.max(1, dates.length / 7);
  const rows: WorkloadRow[] = doctors.map((d) => {
    const who = byDoctor.get(d.name)!;
    return {
      doctor: d.name,
      tier: d.tier,
      subspec: d.subspec ?? null,
      score: who.score + (d.prev_workload ?? 0),
      prevWorkload: d.prev_workload ?? 0,
      deltaMedian: 0,
      hoursPerWeek: who.hours / weeks,
      leaveDays: who.leaveDays,
      daysIdle: who.idle,
    };
  });

  // Δ vs tier median
  const byTier = new Map<string, number[]>();
  for (const r of rows) {
    if (!byTier.has(r.tier)) byTier.set(r.tier, []);
    byTier.get(r.tier)!.push(r.score);
  }
  const medians = new Map<string, number>();
  for (const [tier, scores] of byTier) {
    const sorted = [...scores].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];
    medians.set(tier, median);
  }
  for (const r of rows) {
    r.deltaMedian = r.score - (medians.get(r.tier) ?? 0);
  }

  return rows;
}
