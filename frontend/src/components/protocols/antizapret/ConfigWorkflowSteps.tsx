import { cn } from "@/lib/utils";
import { ArrowRight } from "lucide-react";

function WorkflowStep({
  step,
  label,
  active,
  done,
}: {
  step: number;
  label: string;
  active: boolean;
  done: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition-colors",
        done &&
          "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        active && !done && "border-primary/40 bg-primary/10 font-medium text-primary",
        !active && !done && "border-transparent bg-muted/60 text-muted-foreground",
      )}
    >
      <span
        className={cn(
          "flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold",
          done && "bg-emerald-500 text-white",
          active && !done && "bg-primary text-primary-foreground",
          !active && !done && "bg-muted-foreground/20 text-muted-foreground",
        )}
      >
        {done ? "✓" : step}
      </span>
      {label}
    </div>
  );
}

type ConfigWorkflowStepsProps = {
  dirty: boolean;
  pendingApply: boolean;
};

/** Шаги «Изменить → Сохранить → doall.sh»: подсвечивают текущий этап. */
export default function ConfigWorkflowSteps({
  dirty,
  pendingApply,
}: ConfigWorkflowStepsProps) {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-2 border-t pt-4">
      <span className="mr-1 text-xs text-muted-foreground">Шаги:</span>
      <WorkflowStep step={1} label="Изменить" active={dirty} done={pendingApply} />
      <ArrowRight className="hidden h-3.5 w-3.5 text-muted-foreground/50 sm:block" />
      <WorkflowStep step={2} label="Сохранить" active={dirty} done={pendingApply} />
      <ArrowRight className="hidden h-3.5 w-3.5 text-muted-foreground/50 sm:block" />
      <WorkflowStep step={3} label="doall.sh" active={pendingApply} done={false} />
    </div>
  );
}
