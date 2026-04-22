/**
 * Shows live hard-constraint validation results for the current draft
 * roster. Green chips for rules that pass, red list for violations with
 * rule / location / message.
 */

import { CheckCircle2, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { type ValidationResult } from "@/store/draft";

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
  horizon: "Horizon configured",
};

interface Props {
  result: ValidationResult | null;
  validating: boolean;
  changeCount: number;
}

export function ValidationPanel({ result, validating, changeCount }: Props) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {validating ? (
            <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
          ) : result?.ok ? (
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
          ) : (
            <ShieldAlert className="h-4 w-4 text-rose-600" />
          )}
          <CardTitle>Validation</CardTitle>
        </div>
        <CardDescription>
          {changeCount > 0
            ? `${changeCount} change${changeCount === 1 ? "" : "s"} from the solver's roster. Re-checked after every edit.`
            : "Editing the roster manually. Violations against hard constraints will show up here."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!result ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {validating ? "Checking…" : "Make an edit to run the first check."}
          </p>
        ) : (
          <>
            <div>
              <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Rules satisfied
              </p>
              <div className="flex flex-wrap gap-1">
                {result.rules_passed.length === 0 && (
                  <p className="text-xs text-slate-400">—</p>
                )}
                {result.rules_passed.map((r) => (
                  <span
                    key={r}
                    className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                  >
                    <CheckCircle2 className="h-3 w-3" />
                    {RULE_LABELS[r] ?? r}
                  </span>
                ))}
              </div>
            </div>

            {result.violations.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-rose-600 dark:text-rose-300">
                  Violations ({result.violation_count})
                </p>
                <ul className="space-y-1">
                  {result.violations.map((v, i) => (
                    <li
                      key={i}
                      className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1.5 text-xs dark:border-rose-900 dark:bg-rose-950/50"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-rose-800 dark:text-rose-200">
                          {RULE_LABELS[v.rule] ?? v.rule}
                        </span>
                        <span className="text-[10px] text-rose-700 dark:text-rose-300">
                          {v.location}
                        </span>
                      </div>
                      <p className="mt-0.5 text-rose-900 dark:text-rose-100">{v.message}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {result.ok && (
              <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-100">
                <CheckCircle2 className="mr-1 inline h-3 w-3" />
                Draft meets all enforced hard constraints. (Soft penalties
                still apply — Workload / Score breakdown below.)
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
