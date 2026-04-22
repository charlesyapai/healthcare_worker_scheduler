import { Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  icon?: LucideIcon;
  title: string;
  description: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  actions,
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center dark:border-slate-700 dark:bg-slate-900",
        className,
      )}
    >
      <Icon className="h-8 w-8 text-slate-400" />
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {description}
        </p>
      </div>
      {actions && <div className="flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}
