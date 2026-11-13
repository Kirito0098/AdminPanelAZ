import { CardDescription, CardTitle } from "@/components/ui/card";
import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { GroupedSection } from "./antizapretConfigSchema";

type ConfigSectionHeadingProps = {
  section: GroupedSection;
  /** Правый слот: счётчик включённых флагов секции. */
  badge?: ReactNode;
};

export default function ConfigSectionHeading({
  section,
  badge,
}: ConfigSectionHeadingProps) {
  const SectionIcon = section.icon;

  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <SectionIcon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <CardTitle className="text-base">{section.title}</CardTitle>
          {section.description && (
            <CardDescription className="mt-1">
              {section.description}
            </CardDescription>
          )}
          {section.title === "Cloudflare WARP" && (
            <Link
              to="/protocols/warper"
              className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-4 hover:underline"
            >
              Управление AZ-WARP
              <ArrowRight className="h-3 w-3" />
            </Link>
          )}
        </div>
      </div>
      {badge}
    </div>
  );
}
