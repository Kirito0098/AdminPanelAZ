import { protocolLabel } from "@/lib/vpnTypes";
import type { AntizapretSettingField } from "@/types";
import type { LucideIcon } from "lucide-react";
import {
  Ban,
  Cable,
  Cloud,
  ListFilter,
  Network,
  Route,
  Settings2,
  Shield,
} from "lucide-react";

export type FieldLayout = "list" | "grid";

export interface ConfigSection {
  title: string;
  description?: string;
  keys: string[];
  icon: LucideIcon;
  fieldLayout?: FieldLayout;
}

export type GroupedSection = ConfigSection & { fields: AntizapretSettingField[] };

/** Строки сетки: левый и правый блок на одной линии. */
export const FIELD_LAYOUT: ReadonlyArray<{ left?: string; right?: string }> = [
  { left: "Маршрутизация трафика", right: "Безопасность сервера" },
  { left: "Резервные порты", right: "Cloudflare WARP" },
  { left: "Очистка списков", right: "AdBlock" },
];
export const LAYOUT_BOTTOM = ["Адреса подключения"] as const;

export const PLACED_SECTIONS = new Set<string>([
  ...FIELD_LAYOUT.flatMap((row) =>
    [row.left, row.right].filter((title): title is string => Boolean(title)),
  ),
  ...LAYOUT_BOTTOM,
]);

export const FIELD_DISPLAY: Partial<
  Record<string, { title: string; description: string }>
> = {
  openvpn_host: {
    title: "OpenVPN",
    description:
      "Домен или IP для клиентских конфигов OpenVPN. Не используйте домен панели (DOMAIN) — иначе панель станет недоступна через AZ.",
  },
  wireguard_host: {
    title: protocolLabel("wireguard"),
    description:
      "Домен или IP для клиентских конфигов WireGuard и AmneziaWG. Не используйте домен панели (DOMAIN).",
  },
};

export const FIELD_SECTIONS: ConfigSection[] = [
  {
    title: "Маршрутизация трафика",
    description: "Какие сервисы направлять через AntiZapret VPN",
    icon: Route,
    keys: [
      "route_all",
      "discord_include",
      "cloudflare_include",
      "telegram_include",
      "whatsapp_include",
      "roblox_include",
    ],
  },
  {
    title: "Безопасность сервера",
    description:
      "Защита VPN-сервера от атак и злоупотреблений. Применяется сразу — служба antizapret перезапускается",
    icon: Shield,
    keys: [
      "ssh_protection",
      "attack_protection",
      "scan_protection",
      "flood_protection",
      "torrent_guard",
      "restrict_forward",
      "client_isolation",
    ],
  },
  {
    title: "Резервные порты",
    description:
      `Альтернативные порты ${protocolLabel("openvpn")} и ${protocolLabel("wireguard")} для обхода блокировок`,
    icon: Network,
    keys: ["OPENVPN_BACKUP_TCP", "OPENVPN_BACKUP_UDP", "WIREGUARD_BACKUP"],
  },
  {
    title: "Cloudflare WARP",
    description:
      "Встроенный WARP AntiZapret-VPN (не AZ-WARP). Старый формат y/n в setup поддерживает только None / All, режимы Domain и Custom — на AntiZapret-VPN с 26.10.2026. Списки доменов WARP — в «Редакторе файлов».",
    icon: Cloud,
    keys: [
      "ANTIZAPRET_WARP",
      "VPN_WARP",
      "WARP_PROTECTION",
      "warp_endpoint",
      "WARP_MTU",
      "DNS_WARP",
      "reconnect_warp",
    ],
  },
  {
    title: "AdBlock",
    description: "Блокировка рекламы и трекеров в AntiZapret и полном VPN",
    icon: Ban,
    keys: ["ANTIZAPRET_ADBLOCK", "VPN_ADBLOCK"],
  },
  {
    title: "Подсети клиентов",
    description:
      "Диапазоны адресов клиентов и fake-IP из setup AntiZapret. Смена меняет адреса у всех клиентов: панель перепишет kresd.conf, --fake-cidr в proxy.py и services.env AZ-AWG2, профили придётся пересобрать, клиентам — переподключиться",
    icon: Network,
    keys: ["alternative_client_ip", "alternative_fake_ip"],
  },
  {
    title: "Адреса подключения",
    description:
      "Домены OPENVPN_HOST / WIREGUARD_HOST из setup. Список remote и multihome — на странице OpenVPN.",
    icon: Cable,
    fieldLayout: "grid",
    keys: ["openvpn_host", "wireguard_host"],
  },
  {
    title: "Очистка списков",
    description: "Фильтрация доменов и очистка DNS-кеша при авто-обновлении списков",
    icon: ListFilter,
    keys: ["clear_hosts", "clear_dns_cache"],
  },
];

export function fieldDisplay(field: AntizapretSettingField) {
  const override = FIELD_DISPLAY[field.key];
  return {
    title: override?.title || field.title || field.key,
    description: override?.description || field.description,
  };
}

export function isFlagOn(value: string | undefined): boolean {
  return value?.toLowerCase() === "y";
}

/** Choice-поля WARP: «1» (None) — выключено, остальные значения — включено. */
export function isFieldOn(
  field: AntizapretSettingField,
  value: string | undefined,
): boolean {
  if (field.type === "choice") return Boolean(value) && value !== "1";
  return field.type === "flag" && isFlagOn(value);
}

export function isToggleField(field: AntizapretSettingField): boolean {
  return field.type === "flag" || field.type === "choice";
}

export function groupSchema(schema: AntizapretSettingField[]): GroupedSection[] {
  const byKey = new Map(schema.map((field) => [field.key, field]));
  const used = new Set<string>();
  const sections: GroupedSection[] = FIELD_SECTIONS.map((section) => {
    const fields = section.keys
      .map((key) => byKey.get(key))
      .filter((field): field is AntizapretSettingField => Boolean(field));
    fields.forEach((field) => used.add(field.key));
    return { ...section, fields };
  }).filter((section) => section.fields.length > 0);

  const rest = schema.filter((field) => !used.has(field.key));
  if (rest.length > 0) {
    sections.push({
      title: "Другие параметры",
      description: "Дополнительные настройки setup",
      icon: Settings2,
      keys: [],
      fields: rest,
    });
  }
  return sections;
}

export function indexSectionsByTitle(
  sections: GroupedSection[],
): Map<string, GroupedSection> {
  return new Map(sections.map((section) => [section.title, section]));
}

export function sectionEnabledCount(
  fields: AntizapretSettingField[],
  draft: Record<string, string>,
): { enabled: number; total: number } {
  const flags = fields.filter(isToggleField);
  const enabled = flags.filter((field) => isFieldOn(field, draft[field.key])).length;
  return { enabled, total: flags.length };
}
