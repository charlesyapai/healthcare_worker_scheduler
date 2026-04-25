/**
 * Compact editor for a single (person × day) cell. Shows the current
 * assignments, lets the user remove each, and adds new roles from a
 * dropdown backed by the current station list.
 */

import { X } from "lucide-react";

import type { DoctorEntry, StationEntry } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useState } from "react";
import type { AssignmentRow } from "@/store/solve";

interface Props {
  doctor: DoctorEntry;
  date: string;
  stations: StationEntry[];
  assignments: AssignmentRow[];
  onChange: (next: AssignmentRow[]) => void;
  onClose: () => void;
}

export function CellEditor({
  doctor,
  date,
  stations,
  assignments,
  onChange,
  onClose,
}: Props) {
  const [selected, setSelected] = useState("");

  const rolesAvailable = buildRoleOptions(stations, doctor);

  const removeRole = (role: string) => {
    onChange(assignments.filter((a) => a.role !== role));
  };

  const addRole = () => {
    if (!selected) return;
    if (assignments.some((a) => a.role === selected)) return;
    onChange([...assignments, { doctor: doctor.name, date, role: selected }]);
    setSelected("");
  };

  return (
    <div
      className="w-72 rounded-md border border-slate-200 bg-white p-3 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-950"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold leading-tight">{doctor.name}</p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            {doctor.tier} · {date}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-label="Close"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="mb-2">
        <p className="mb-1 text-[11px] font-medium text-slate-600 dark:text-slate-300">
          Current assignments
        </p>
        {assignments.length === 0 ? (
          <p className="text-[11px] text-slate-500 dark:text-slate-400">None.</p>
        ) : (
          <ul className="space-y-1">
            {assignments.map((a) => (
              <li
                key={a.role}
                className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-2 py-1 dark:border-slate-800 dark:bg-slate-900"
              >
                <span className="font-mono">{humanize(a.role)}</span>
                <button
                  type="button"
                  onClick={() => removeRole(a.role)}
                  className="rounded-md p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-800"
                  aria-label="Remove"
                >
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <p className="mb-1 text-[11px] font-medium text-slate-600 dark:text-slate-300">
          Add role
        </p>
        <div className="flex gap-2">
          <Select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="h-7 flex-1 text-xs"
          >
            <option value="">pick…</option>
            {rolesAvailable.map((r) => (
              <option key={r} value={r}>
                {humanize(r)}
              </option>
            ))}
          </Select>
          <Button size="sm" onClick={addRole} disabled={!selected}>
            Add
          </Button>
        </div>
      </div>
    </div>
  );
}

function buildRoleOptions(stations: StationEntry[], doctor: DoctorEntry): string[] {
  const roles: string[] = [];
  for (const s of stations) {
    if (!s.name) continue;
    // Per Phase A: per-doctor eligibility is the truth. station.eligible_tiers
    // is advisory only — not enforced when offering role options.
    if (!doctor.eligible_stations?.includes(s.name)) continue;
    for (const sess of s.sessions ?? []) {
      roles.push(`STATION_${s.name}_${sess}`);
    }
  }
  if (doctor.tier !== "consultant") {
    roles.push("ONCALL", "WEEKEND_EXT");
  } else {
    roles.push("WEEKEND_CONSULT");
  }
  return roles;
}

function humanize(role: string): string {
  if (role === "ONCALL") return "On-call";
  if (role === "WEEKEND_EXT") return "Weekend EXT";
  if (role === "WEEKEND_CONSULT") return "Weekend consultant";
  if (role.startsWith("STATION_")) {
    const inner = role.slice(8);
    const parts = inner.split("_");
    const sess = parts.pop();
    return `${parts.join("_")} · ${sess}`;
  }
  return role;
}
