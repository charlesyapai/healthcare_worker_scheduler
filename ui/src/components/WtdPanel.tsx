/**
 * UK WTD compliance receipt for a caller-provided roster.
 *
 * Posts to /api/compliance/uk_wtd whenever the viewed roster changes.
 * Green = statutorily compliant under the UK junior-doctor 2016 contract
 * + EU WTD default thresholds; red = at least one hard breach (W1–W4);
 * amber = soft breach only (W5/W6 consecutive-long-days/nights).
 *
 * This is reporting-only — the solver does NOT enforce these rules
 * today. See `docs/INDUSTRY_CONTEXT.md §5` for the rationale.
 */

import { AlertTriangle, CheckCircle2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useComputeWtd, type WtdViolation } from "@/api/hooks";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { type AssignmentRow } from "@/store/solve";

const RULE_LABELS: Record<string, string> = {
  W1_AVG_WEEKLY_HOURS: "W1 — 48h weekly average",
  W2_ROLLING_7_DAYS: "W2 — 72h rolling 7 days",
  W3_MAX_SHIFT_HOURS: "W3 — 13h per shift",
  W4_MIN_REST_BETWEEN: "W4 — 11h rest between shifts",
  W5_CONSECUTIVE_LONG_DAYS: "W5 — max 4 consecutive long days",
  W6_CONSECUTIVE_NIGHTS: "W6 — max 7 consecutive nights",
};

interface Props {
  assignments: AssignmentRow[];
}

export function WtdPanel({ assignments }: Props) {
  const wtd = useComputeWtd();
  const [expanded, setExpanded] = useState(false);

  const signature = useMemo(() => {
    if (assignments.length === 0) return "empty";
    return `${assignments.length}:${assignments[0]?.doctor}:${
      assignments[assignments.length - 1]?.role
    }:${assignments[assignments.length - 1]?.date}`;
  }, [assignments]);

  useEffect(() => {
    if (assignments.length === 0) return;
    wtd.mutate(assignments);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  if (assignments.length === 0) return null;

  const data = wtd.data;

  let tone: "ok" | "warn" | "fail" = "ok";
  if (data) {
    if (data.error_count > 0) tone = "fail";
    else if (data.warning_count > 0) tone = "warn";
  }

  const Icon = tone === "fail" ? ShieldAlert : tone === "warn" ? AlertTriangle : ShieldCheck;
  const tint =
    tone === "fail"
      ? "border-rose-300 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/40"
      : tone === "warn"
        ? "border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40"
        : "border-emerald-300 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40";
  const iconTint =
    tone === "fail"
      ? "text-rose-600 dark:text-rose-300"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-300"
        : "text-emerald-600 dark:text-emerald-300";

  return (
    <Card className={cn(tint)}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Icon className={cn("h-4 w-4", iconTint)} />
          <CardTitle className="text-sm">UK WTD compliance</CardTitle>
        </div>
        <CardDescription className="text-xs">
          UK junior-doctor 2016 + EU WTD audit. Reporting-only — the
          solver does not enforce these rules. See{" "}
          <code>docs/INDUSTRY_CONTEXT.md §5</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        {wtd.isPending && (
          <p className="text-slate-500 dark:text-slate-400">Checking…</p>
        )}
        {data && (
          <>
            <div className="flex flex-wrap gap-2">
              <Badge ok={data.ok}>
                {data.ok ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    WTD-compliant
                  </>
                ) : (
                  <>
                    <ShieldAlert className="h-3.5 w-3.5" />
                    {data.violation_count} breach
                    {data.violation_count === 1 ? "" : "es"}
                  </>
                )}
              </Badge>
              {data.error_count > 0 && (
                <Badge tone="fail">{data.error_count} error</Badge>
              )}
              {data.warning_count > 0 && (
                <Badge tone="warn">{data.warning_count} warning</Badge>
              )}
            </div>

            {data.violation_count > 0 && (
              <RuleSummary by_rule={data.by_rule} />
            )}

            {data.violation_count > 0 && (
              <>
                <button
                  type="button"
                  className="text-[11px] font-medium text-indigo-600 underline decoration-dotted underline-offset-2 hover:text-indigo-500 dark:text-indigo-300"
                  onClick={() => setExpanded((v) => !v)}
                >
                  {expanded ? "Hide" : "Show"} detail
                </button>
                {expanded && <ViolationTable violations={data.violations} />}
              </>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Badge({
  children,
  ok,
  tone,
}: {
  children: React.ReactNode;
  ok?: boolean;
  tone?: "fail" | "warn";
}) {
  const resolved = tone ?? (ok ? "ok" : "fail");
  const color =
    resolved === "ok"
      ? "border-emerald-300 bg-emerald-100 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
      : resolved === "warn"
        ? "border-amber-300 bg-amber-100 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"
        : "border-rose-300 bg-rose-100 text-rose-700 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        color,
      )}
    >
      {children}
    </span>
  );
}

function RuleSummary({ by_rule }: { by_rule: Record<string, number> }) {
  const rows = Object.entries(by_rule).sort((a, b) => b[1] - a[1]);
  if (rows.length === 0) return null;
  return (
    <div className="space-y-1">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        Breaches by rule
      </div>
      <ul className="space-y-0.5 text-[11px]">
        {rows.map(([rule, count]) => (
          <li key={rule} className="flex items-center justify-between">
            <span>{RULE_LABELS[rule] ?? rule}</span>
            <span className="font-mono font-semibold">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ViolationTable({ violations }: { violations: WtdViolation[] }) {
  return (
    <div className="mt-1 max-h-64 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
      <table className="w-full text-[11px]">
        <thead className="bg-slate-100 dark:bg-slate-900">
          <tr className="text-left text-slate-500 dark:text-slate-400">
            <th className="px-2 py-1">Doctor</th>
            <th className="px-2 py-1">Rule</th>
            <th className="px-2 py-1">Message</th>
          </tr>
        </thead>
        <tbody>
          {violations.map((v, i) => (
            <tr
              key={i}
              className={cn(
                "border-t border-slate-200 dark:border-slate-800",
                v.severity === "error"
                  ? "bg-rose-50/40 dark:bg-rose-950/10"
                  : "bg-amber-50/40 dark:bg-amber-950/10",
              )}
            >
              <td className="px-2 py-1 font-mono">{v.doctor}</td>
              <td className="px-2 py-1 font-mono">
                {RULE_LABELS[v.rule]?.replace(/^W\d+\s*—\s*/, "") ?? v.rule}
              </td>
              <td className="px-2 py-1">{v.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
