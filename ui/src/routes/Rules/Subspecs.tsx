import { X } from "lucide-react";
import { useState } from "react";

import { useAutoSavePatch } from "@/api/autosave";
import { useSessionState } from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function Subspecs() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const subspecs = data?.subspecs ?? [];
  const [draft, setDraft] = useState("");

  const add = () => {
    const name = draft.trim();
    if (!name || subspecs.includes(name)) return;
    save({ subspecs: [...subspecs, name] });
    setDraft("");
  };

  const remove = (name: string) =>
    save({ subspecs: subspecs.filter((s) => s !== name) });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sub-specialties</CardTitle>
        <CardDescription>
          Consultant sub-specialty labels. Weekend coverage (H8) requires one
          consultant per sub-spec, so this must match your actual mix.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {subspecs.map((s) => (
            <span
              key={s}
              className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-3 py-1 text-sm font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300"
            >
              {s}
              <button
                type="button"
                aria-label={`Remove ${s}`}
                className="rounded-full p-0.5 hover:bg-indigo-200 dark:hover:bg-indigo-900"
                onClick={() => remove(s)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <Input
            placeholder="e.g. Neuro"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            className="max-w-xs"
          />
          <Button variant="secondary" size="sm" onClick={add} disabled={!draft.trim()}>
            Add
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
