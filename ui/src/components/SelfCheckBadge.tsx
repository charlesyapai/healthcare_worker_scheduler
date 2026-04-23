/**
 * Automated post-solve hard-constraint audit badge.
 *
 * The server runs the same validator (`api/validator.py`) over every
 * solver output and returns the result alongside the roster. A green
 * badge is the feasibility receipt that lets researchers and roster
 * coordinators trust a run without reading source. A red badge means
 * the CP-SAT model and the validator disagree — always a bug.
 */

import { CheckCircle2, ShieldAlert, ShieldCheck } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { type SolverSelfCheck } from "@/store/solve";

const RULE_LABELS: Record<string, string> = {
  H1: "H1 Station coverage",
  H2: "H2 One station per session",
  H3: "H3 Eligibility",
  H4: "H4 On-call 1-in-N cap",
  H5: "H5 Post-call off",
  H8: "H8 Weekend coverage",
  H10: "H10 Leave honoured",
  H12: "H12 No-on-call block",
  H13: "H13 Session block",
  weekday_oc: "Weekday on-call coverage",
};

export function SelfCheckBadge({ selfCheck }: { selfCheck: SolverSelfCheck | null | undefined }) {
  if (!selfCheck) {
    return (
      <Card>
        <CardContent className="py-3 text-xs text-slate-500 dark:text-slate-400">
          Self-check not run (solver returned no roster).
        </CardContent>
      </Card>
    );
  }

  if (selfCheck.ok) {
    return (
      <Card className="border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/60">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <CardTitle className="text-sm">Solver self-check: all hard constraints satisfied</CardTitle>
          </div>
          <CardDescription>
            The post-solve validator re-checked every rule on the returned
            roster. Cross-reference: <code>docs/CONSTRAINTS.md §2</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex flex-wrap gap-1">
            {selfCheck.rules_passed.map((r) => (
              <span
                key={r}
                className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-800 dark:bg-emerald-900/70 dark:text-emerald-100"
              >
                <CheckCircle2 className="h-3 w-3" />
                {RULE_LABELS[r] ?? r}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Red path: model and validator disagree. Loud on purpose — this is the
  // tripwire the validation plan specifies.
  return (
    <Card className="border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/60">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-rose-600 dark:text-rose-300" />
          <CardTitle className="text-sm">
            Solver self-check FAILED — {selfCheck.violation_count} violation
            {selfCheck.violation_count === 1 ? "" : "s"}
          </CardTitle>
        </div>
        <CardDescription className="text-rose-900 dark:text-rose-200">
          The CP-SAT model and the post-solve validator disagree. Treat this
          as a bug; do not publish this roster. Report with the SHA from{" "}
          <code>/api/health</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 pt-0 text-xs">
        <div className="flex flex-wrap gap-1">
          {selfCheck.rules_failed.map((r) => (
            <span
              key={r}
              className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-semibold text-rose-800 dark:bg-rose-900/70 dark:text-rose-100"
            >
              {RULE_LABELS[r] ?? r}
            </span>
          ))}
        </div>
        <ul className="mt-1 space-y-1">
          {selfCheck.violations.slice(0, 8).map((v, i) => (
            <li
              key={i}
              className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 dark:border-rose-900 dark:bg-rose-950/50"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-rose-800 dark:text-rose-100">
                  {RULE_LABELS[v.rule] ?? v.rule}
                </span>
                <span className="text-[10px] text-rose-700 dark:text-rose-200">
                  {v.location}
                </span>
              </div>
              <p className="mt-0.5 text-rose-900 dark:text-rose-100">{v.message}</p>
            </li>
          ))}
          {selfCheck.violations.length > 8 && (
            <li className="text-[10px] text-rose-700 dark:text-rose-200">
              …and {selfCheck.violations.length - 8} more.
            </li>
          )}
        </ul>
      </CardContent>
    </Card>
  );
}
