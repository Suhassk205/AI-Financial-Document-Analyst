import { clsx } from "clsx";
import { Inbox } from "lucide-react";

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

/** Friendly empty state with icon and optional CTA. */
export default function EmptyState({
  title = "Nothing here yet",
  description = "Upload a document or run an analysis to get started.",
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={clsx(
        "glass-panel flex flex-col items-center justify-center py-16 px-6 text-center animate-fade-in",
        className,
      )}
      role="status"
    >
      <div className="w-16 h-16 rounded-full bg-brand-50 dark:bg-brand-900/30 ring-8 ring-brand-50/50 dark:ring-brand-900/10 flex items-center justify-center mb-5 transition-all">
        {icon ?? <Inbox className="w-8 h-8 text-brand-500 dark:text-brand-400" />}
      </div>
      <h3 className="text-base font-semibold text-surface-700 dark:text-surface-300">{title}</h3>
      <p className="text-sm text-surface-500 dark:text-surface-500 mt-1 max-w-sm">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
