import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import ConfigFieldRow from "./ConfigFieldRow";
import ConfigSectionHeading from "./ConfigSectionHeading";
import {
  sectionEnabledCount,
  type GroupedSection,
} from "./antizapretConfigSchema";

type ConfigSectionCardProps = {
  section: GroupedSection;
  draft: Record<string, string>;
  dirtySet: Set<string>;
  disabled: boolean;
  onDraftChange: (key: string, value: string) => void;
};

export default function ConfigSectionCard({
  section,
  draft,
  dirtySet,
  disabled,
  onDraftChange,
}: ConfigSectionCardProps) {
  const { enabled, total } = sectionEnabledCount(section.fields, draft);
  const useGrid =
    section.fieldLayout === "grid" &&
    section.fields.length > 1 &&
    section.fields.every((field) => field.type === "string");

  return (
    <Card
      id={`section-${section.title}`}
      className="flex h-full flex-col overflow-hidden"
    >
      <CardHeader className="pb-3">
        <ConfigSectionHeading
          section={section}
          badge={
            total > 0 ? (
              <Badge variant="secondary" className="shrink-0 tabular-nums">
                {enabled}/{total}
              </Badge>
            ) : undefined
          }
        />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col p-0">
        <div
          className={cn(
            "flex flex-1 flex-col border-t",
            useGrid
              ? "grid grid-cols-1 divide-y sm:grid-cols-2 sm:divide-x sm:divide-y-0"
              : "divide-y",
          )}
        >
          {section.fields.map((field) => (
            <ConfigFieldRow
              key={field.key}
              field={field}
              value={draft[field.key] ?? ""}
              dirty={dirtySet.has(field.key)}
              disabled={disabled}
              onChange={(value) => onDraftChange(field.key, value)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
