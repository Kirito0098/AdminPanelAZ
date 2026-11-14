import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { AntizapretSettingField } from "@/types";
import { fieldDisplay, isFlagOn } from "./antizapretConfigSchema";

type ConfigFieldRowProps = {
  field: AntizapretSettingField;
  value: string;
  dirty: boolean;
  disabled: boolean;
  onChange: (value: string) => void;
};

function DirtyBadge() {
  return (
    <Badge
      variant="outline"
      className="border-amber-500/40 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-300"
    >
      изменено
    </Badge>
  );
}

/** Одна строка параметра setup: switch для flag, select для choice, input для остальных. */
export default function ConfigFieldRow({
  field,
  value,
  dirty,
  disabled,
  onChange,
}: ConfigFieldRowProps) {
  const id = field.html_id || field.key;
  const display = fieldDisplay(field);
  const isSwitchRow = field.type === "flag";
  const isSelectRow = field.type === "choice";
  const isNumber = field.type === "number";
  const enabled = isFlagOn(value);
  const options = field.options ?? [];
  const knownOption = options.some((opt) => opt.value === value);

  return (
    <div
      className={cn(
        isSwitchRow
          ? "flex items-start justify-between gap-4 px-4 py-3.5 transition-colors sm:px-5"
          : cn("space-y-2 px-4 sm:px-5", isSelectRow ? "py-3.5" : "py-4"),
        dirty && "bg-amber-500/5",
        isSwitchRow && !disabled && "hover:bg-muted/30",
      )}
    >
      <div className={isSwitchRow ? "min-w-0 flex-1 space-y-1" : "space-y-1"}>
        <div className="flex flex-wrap items-center gap-2">
          <Label
            htmlFor={id}
            className={
              isSwitchRow
                ? "cursor-pointer font-medium leading-snug"
                : isSelectRow
                  ? "font-medium leading-snug"
                  : undefined
            }
          >
            {display.title}
          </Label>
          {dirty && <DirtyBadge />}
        </div>
        {display.description && (
          <p
            className={cn(
              "text-xs text-muted-foreground",
              (isSwitchRow || isSelectRow) && "leading-relaxed",
            )}
          >
            {display.description}
          </p>
        )}
        <p className="font-mono text-[10px] text-muted-foreground/70">
          {field.param_label || field.env}
        </p>
      </div>

      {isSwitchRow && (
        <Switch
          id={id}
          checked={enabled}
          disabled={disabled}
          className="mt-0.5"
          aria-label={`${display.title}: ${enabled ? "включено" : "выключено"}`}
          onCheckedChange={(checked) => onChange(checked ? "y" : "n")}
        />
      )}

      {isSelectRow && (
        <Select value={value} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger id={id} className="w-full">
            <SelectValue placeholder={field.env} />
          </SelectTrigger>
          <SelectContent>
            {!knownOption && value && (
              <SelectItem value={value} disabled>
                {value} — нестандартное значение
              </SelectItem>
            )}
            {options.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.value}) {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {!isSwitchRow && !isSelectRow && (
        <Input
          id={id}
          type={isNumber ? "number" : undefined}
          inputMode={isNumber ? "numeric" : undefined}
          min={isNumber ? (field.min ?? undefined) : undefined}
          max={isNumber ? (field.max ?? undefined) : undefined}
          value={value}
          disabled={disabled}
          placeholder={
            isNumber
              ? field.placeholder
                ? `По умолчанию ${field.placeholder}`
                : field.env
              : field.placeholder || field.env
          }
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}
