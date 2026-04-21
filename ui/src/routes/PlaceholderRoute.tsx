import { Construction } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Props {
  title: string;
  phase: string;
  description: string;
  todo: string[];
}

export function PlaceholderRoute({ title, phase, description, todo }: Props) {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <div className="mb-1 inline-flex items-center gap-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <Construction className="h-3 w-3" />
          {phase}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {description}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>What's coming</CardTitle>
          <CardDescription>{phase} items from the UI plan.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-300">
            {todo.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
