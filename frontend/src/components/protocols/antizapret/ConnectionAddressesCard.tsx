import { firstNonEmptyRemoteHost } from "@/components/proxy/RemoteHostsCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { protocolLabel } from "@/lib/vpnTypes";
import { Link } from "react-router-dom";
import ConfigSectionHeading from "./ConfigSectionHeading";
import { fieldDisplay, type GroupedSection } from "./antizapretConfigSchema";

type ConnectionAddressesCardProps = {
  section: GroupedSection;
  draft: Record<string, string>;
  dirtySet: Set<string>;
  disabled: boolean;
  onDraftChange: (key: string, value: string) => void;
  savedRemoteHosts: string[];
  applyFirstRemoteToWireguard: boolean;
};

/** OPENVPN_HOST / WIREGUARD_HOST: показываем подсказку «из списка», если адрес приходит из remote. */
export default function ConnectionAddressesCard({
  section,
  draft,
  dirtySet,
  disabled,
  onDraftChange,
  savedRemoteHosts,
  applyFirstRemoteToWireguard,
}: ConnectionAddressesCardProps) {
  const openvpnField = section.fields.find((field) => field.key === "openvpn_host");
  const wireguardField = section.fields.find((field) => field.key === "wireguard_host");
  const syncedOpenvpnHost = firstNonEmptyRemoteHost(savedRemoteHosts);
  const listSynced = Boolean(syncedOpenvpnHost);
  const wireguardSynced = listSynced && applyFirstRemoteToWireguard;

  return (
    <Card
      id={`section-${section.title}`}
      className="flex h-full flex-col overflow-hidden"
    >
      <CardHeader className="pb-3">
        <ConfigSectionHeading section={section} />
      </CardHeader>
      <CardContent className="flex flex-1 flex-col p-0">
        <div className="grid grid-cols-1 divide-y border-t sm:grid-cols-2 sm:divide-x sm:divide-y-0">
          {openvpnField && (
            <div
              className={cn(
                "space-y-2 px-4 py-4 sm:px-5",
                !listSynced && dirtySet.has("openvpn_host") && "bg-amber-500/5",
              )}
            >
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Label htmlFor={openvpnField.html_id || openvpnField.key}>
                    {fieldDisplay(openvpnField).title}
                  </Label>
                  {!listSynced && dirtySet.has("openvpn_host") && (
                    <Badge
                      variant="outline"
                      className="border-amber-500/40 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-300"
                    >
                      изменено
                    </Badge>
                  )}
                  {listSynced && (
                    <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                      из списка
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {listSynced
                    ? "Первый адрес списка remote при сохранении записывается в OPENVPN_HOST. Поле setup здесь только для просмотра."
                    : fieldDisplay(openvpnField).description}
                </p>
                <p className="font-mono text-[10px] text-muted-foreground/70">
                  {openvpnField.param_label || openvpnField.env}
                </p>
              </div>
              <Input
                id={openvpnField.html_id || openvpnField.key}
                value={
                  listSynced ? (syncedOpenvpnHost ?? "") : (draft.openvpn_host ?? "")
                }
                disabled={disabled || listSynced}
                readOnly={listSynced}
                placeholder={openvpnField.env}
                onChange={(e) => onDraftChange("openvpn_host", e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Несколько remote — на странице{" "}
                <Link
                  to="/protocols/openvpn"
                  className="font-medium text-primary underline-offset-4 hover:underline"
                >
                  OpenVPN (панель) →
                </Link>
              </p>
            </div>
          )}
          {wireguardField && (
            <div
              className={cn(
                "space-y-2 px-4 py-4 sm:px-5",
                !wireguardSynced && dirtySet.has("wireguard_host") && "bg-amber-500/5",
              )}
            >
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Label htmlFor={wireguardField.html_id || wireguardField.key}>
                    {fieldDisplay(wireguardField).title}
                  </Label>
                  {!wireguardSynced && dirtySet.has("wireguard_host") && (
                    <Badge
                      variant="outline"
                      className="border-amber-500/40 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-300"
                    >
                      изменено
                    </Badge>
                  )}
                  {wireguardSynced && (
                    <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                      из списка
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {wireguardSynced
                    ? `Первый адрес списка remote при сохранении записывается в WIREGUARD_HOST (прокси для ${protocolLabel("wireguard")}). Поле setup здесь только для просмотра.`
                    : fieldDisplay(wireguardField).description}
                </p>
                <p className="font-mono text-[10px] text-muted-foreground/70">
                  {wireguardField.param_label || wireguardField.env}
                </p>
              </div>
              <Input
                id={wireguardField.html_id || wireguardField.key}
                value={
                  wireguardSynced
                    ? (syncedOpenvpnHost ?? "")
                    : (draft.wireguard_host ?? "")
                }
                disabled={disabled || wireguardSynced}
                readOnly={wireguardSynced}
                placeholder={wireguardField.env}
                onChange={(e) => onDraftChange("wireguard_host", e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {wireguardSynced
                  ? "Галочка «Также для WG/AWG 1.5 / AWG 2.0» на странице OpenVPN."
                  : "Несколько адресов пока только для OpenVPN. Для прокси GubernievS включите галочку на странице OpenVPN."}
              </p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
