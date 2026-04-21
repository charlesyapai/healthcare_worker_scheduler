import { useAutoSavePatch } from "@/api/autosave";
import { useSessionState } from "@/api/hooks";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function Tiers() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const labels = data?.tier_labels ?? {
    junior: "Junior",
    senior: "Senior",
    consultant: "Consultant",
  };

  const update = (key: keyof typeof labels, value: string) =>
    save({ tier_labels: { ...labels, [key]: value } });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tier labels</CardTitle>
        <CardDescription>
          Rename the three internal tiers to your hospital's terminology. Labels
          appear in the workload table and verdict banner; solver logic still
          targets junior / senior / consultant.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-3">
        {(["junior", "senior", "consultant"] as const).map((tier) => (
          <label key={tier} className="flex flex-col gap-1">
            <span className="text-sm font-medium capitalize">{tier}</span>
            <Input
              value={labels[tier]}
              onChange={(e) => update(tier, e.target.value)}
            />
          </label>
        ))}
      </CardContent>
    </Card>
  );
}
