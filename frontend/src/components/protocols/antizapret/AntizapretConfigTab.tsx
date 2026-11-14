import {
  ApiError,
  applyRouting,
  getAntizapretSettings,
  getNodeRemoteHosts,
  getVpnNetworkSettings,
  updateAntizapretSettings,
} from "@/api/client";
import HaReplicaBanner from "@/components/dashboard/HaReplicaBanner";
import { firstNonEmptyRemoteHost } from "@/components/proxy/RemoteHostsCard";
import SettingsAlert from "@/components/settings/SettingsAlert";
import ConfirmDialog, { ConfirmDialogHost } from "@/components/shared/ConfirmDialog";
import PageSectionHeader from "@/components/shared/PageSectionHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import EmptyState from "@/components/ui/EmptyState";
import { InlineProgressBar } from "@/components/ui/ProgressBar";
import Spinner from "@/components/ui/Spinner";
import { useNode } from "@/context/NodeContext";
import { useNotifications } from "@/context/NotificationContext";
import { useProgress } from "@/context/ProgressContext";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";
import { useHaReplicaReadonly } from "@/hooks/useHaReplicaReadonly";
import { DOCS } from "@/lib/docsUrls";
import { cn } from "@/lib/utils";
import type { AntizapretSettingField, VpnNetworkSettings } from "@/types";
import { Globe, Play, RefreshCw, Save, Server, Settings2 } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import ConfigSectionCard from "./ConfigSectionCard";
import ConfigWorkflowSteps from "./ConfigWorkflowSteps";
import ConnectionAddressesCard from "./ConnectionAddressesCard";
import {
  FIELD_LAYOUT,
  LAYOUT_BOTTOM,
  PLACED_SECTIONS,
  groupSchema,
  indexSectionsByTitle,
  isFieldOn,
  isFlagOn,
} from "./antizapretConfigSchema";

function envRowValue(
  rows: VpnNetworkSettings["env_rows"],
  labelPrefix: string,
): string {
  const row = rows.find((r) => r.label.startsWith(labelPrefix));
  return row && row.value !== "—" ? row.value : "";
}

function panelHttpsPortIs443(port: string | undefined): boolean {
  const normalized = (port || "").trim() || "443";
  return normalized === "443";
}

export default function AntizapretConfigTab() {
  const { activeNode, loading: nodeLoading } = useNode();
  const { success, error: notifyError, warning: notifyWarning } = useNotifications();
  const { trackBackgroundTask, backgroundTask } = useProgress();
  const haReplicaReadonly = useHaReplicaReadonly();
  const { confirm, dialogProps } = useConfirmDialog();

  const [schema, setSchema] = useState<AntizapretSettingField[]>([]);
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [nodeName, setNodeName] = useState<string | null>(null);
  const [httpsPublicPort, setHttpsPublicPort] = useState("443");
  // Список remote читается только для подсказки «из списка»: правится он на странице OpenVPN.
  const [savedRemoteHosts, setSavedRemoteHosts] = useState<string[]>([]);
  const [applyFirstRemoteToWireguard, setApplyFirstRemoteToWireguard] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // applying висит до onComplete/onError фоновой задачи doall.sh, а не до ответа API.
  const [applying, setApplying] = useState(false);
  const [applyingTaskId, setApplyingTaskId] = useState<string | null>(null);
  const [needsApply, setNeedsApply] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);

  const controlsDisabled = saving || applying || haReplicaReadonly;
  const httpsIs443 = panelHttpsPortIs443(httpsPublicPort);
  const backupTcpPortConflict = httpsIs443 && isFlagOn(draft.OPENVPN_BACKUP_TCP);
  const openvpnHostLockedByList = Boolean(firstNonEmptyRemoteHost(savedRemoteHosts));

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    const nodeId = activeNode?.id ?? null;
    try {
      const [data, vpn, remotes] = await Promise.all([
        getAntizapretSettings(),
        getVpnNetworkSettings().catch(() => null),
        nodeId != null ? getNodeRemoteHosts(nodeId).catch(() => null) : null,
      ]);
      setSchema(data.schema);
      setSaved(data.settings);
      setDraft(data.settings);
      setNodeName(data.node_name ?? activeNode?.name ?? null);
      setNeedsApply(false);
      if (vpn) {
        setHttpsPublicPort(envRowValue(vpn.env_rows, "HTTPS_PUBLIC_PORT") || "443");
      } else {
        setHttpsPublicPort("443");
      }
      setSavedRemoteHosts(remotes?.hosts ?? []);
      setApplyFirstRemoteToWireguard(Boolean(remotes?.apply_to_wireguard));
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Не удалось загрузить настройки AntiZapret";
      setLoadError(message);
      notifyError(message);
    } finally {
      setLoading(false);
    }
  }, [activeNode?.id, activeNode?.name, notifyError]);

  useEffect(() => {
    if (nodeLoading) return;
    void load();
  }, [load, nodeLoading, activeNode?.id]);

  const sections = useMemo(() => groupSchema(schema), [schema]);
  const sectionsByTitle = useMemo(() => indexSectionsByTitle(sections), [sections]);
  const extraSections = useMemo(
    () => sections.filter((section) => !PLACED_SECTIONS.has(section.title)),
    [sections],
  );

  const dirtyKeys = useMemo(
    () =>
      schema
        .filter((field) => {
          if (field.key === "openvpn_host" && openvpnHostLockedByList) return false;
          return draft[field.key] !== saved[field.key];
        })
        .map((field) => field.key),
    [schema, draft, saved, openvpnHostLockedByList],
  );
  const dirty = dirtyKeys.length > 0;
  const dirtySet = useMemo(() => new Set(dirtyKeys), [dirtyKeys]);

  const handleDraftChange = useCallback(
    (key: string, value: string) => {
      if (key === "OPENVPN_BACKUP_TCP" && value === "y" && httpsIs443) {
        confirm({
          title: "Конфликт с портом 443",
          description: (
            <>
              Резервные TCP-порты OpenVPN включают <strong>443</strong>, который уже
              занят HTTPS панели (nginx). Сначала смените «Публичный порт HTTPS» в{" "}
              <Link
                to="/settings/vpn_network"
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                Настройки → Адрес сайта и HTTPS
              </Link>
              , иначе после «Применить» (doall.sh) панель станет недоступна.
            </>
          ),
          confirmLabel: "Всё равно включить",
          alert: {
            variant: "warning",
            title: "Панель на 443",
            children:
              "Можно включить флаг, но доступ к панели по HTTPS на 443 пропадёт, пока OpenVPN слушает этот порт.",
          },
          onConfirm: () => setDraft((prev) => ({ ...prev, OPENVPN_BACKUP_TCP: "y" })),
        });
        return;
      }
      setDraft((prev) => ({ ...prev, [key]: value }));
    },
    [confirm, httpsIs443],
  );

  const renderSection = (title: string) => {
    const section = sectionsByTitle.get(title);
    if (!section) return null;
    if (title === "Адреса подключения") {
      return (
        <ConnectionAddressesCard
          key={section.title}
          section={section}
          draft={draft}
          dirtySet={dirtySet}
          disabled={controlsDisabled}
          onDraftChange={handleDraftChange}
          savedRemoteHosts={savedRemoteHosts}
          applyFirstRemoteToWireguard={applyFirstRemoteToWireguard}
        />
      );
    }
    return (
      <ConfigSectionCard
        key={section.title}
        section={section}
        draft={draft}
        dirtySet={dirtySet}
        disabled={controlsDisabled}
        onDraftChange={handleDraftChange}
      />
    );
  };

  const enabledFlags = useMemo(
    () => schema.filter((field) => isFieldOn(field, draft[field.key])).length,
    [schema, draft],
  );

  const save = async () => {
    if (!dirty) return;
    setSaving(true);
    try {
      const updates = Object.fromEntries(dirtyKeys.map((key) => [key, draft[key]]));
      const result = await updateAntizapretSettings(updates);
      const refreshed = await getAntizapretSettings();
      setSaved(refreshed.settings);
      setDraft(refreshed.settings);
      setNeedsApply(result.needs_apply);
      success(result.message);
      if (result.antizapret_restarted) {
        success("Служба antizapret перезапущена — правила iptables/WARP применены");
      }
      for (const w of result.warnings ?? []) {
        notifyWarning(w);
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : "Ошибка сохранения настроек");
    } finally {
      setSaving(false);
    }
  };

  const finishApply = useCallback(() => {
    setApplying(false);
    setApplyingTaskId(null);
  }, []);

  const apply = async () => {
    if (applying) return;
    setApplying(true);
    try {
      const resp = await applyRouting();
      setApplyingTaskId(resp.task_id);
      trackBackgroundTask(resp.task_id, {
        onComplete: () => {
          finishApply();
          setNeedsApply(false);
          success(resp.message || "Маршрутизация применена (doall.sh)");
          setApplyOpen(false);
        },
        onError: (task, message) => {
          finishApply();
          notifyError(task?.error || task?.message || message);
        },
      });
    } catch (err) {
      finishApply();
      notifyError(
        err instanceof ApiError ? err.message : "Ошибка применения конфигурации",
      );
    }
  };

  // Страховка: если колбэки трекера перезаписала другая задача, кнопка гаснет по статусу.
  useEffect(() => {
    if (!applyingTaskId || backgroundTask?.task_id !== applyingTaskId) return;
    if (backgroundTask.status === "completed" || backgroundTask.status === "failed") {
      finishApply();
    }
  }, [applyingTaskId, backgroundTask, finishApply]);

  const resetDraft = () => {
    setDraft(saved);
  };

  const pendingApply = needsApply && !dirty;

  if (loading) {
    return (
      <div className="space-y-6">
        <HaReplicaBanner />
        <Spinner label="Загрузка конфигурации AntiZapret..." className="py-12" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <HaReplicaBanner />
      <InlineProgressBar active={saving} label="Сохранение настроек..." />
      <InlineProgressBar active={applying} label="Применение doall.sh..." />

      {loadError ? (
        <div className="space-y-4">
          <SettingsAlert variant="danger" title="Ошибка загрузки">
            {loadError}
          </SettingsAlert>
          <Button type="button" variant="secondary" onClick={() => void load()}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Повторить
          </Button>
        </div>
      ) : schema.length === 0 ? (
        <EmptyState
          icon={Settings2}
          title="Нет параметров конфигурации"
          description="API не вернул схему настроек AntiZapret."
        />
      ) : (
        <>
          <div className="relative overflow-hidden rounded-2xl border border-border/80 bg-gradient-to-br from-primary/5 via-card to-card p-5 shadow-sm">
            <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
            <div className="relative">
              <PageSectionHeader
                card={false}
                icon={Globe}
                title="AntiZapret"
                titleAddon={
                  <>
                    {nodeName && (
                      <Badge variant="outline" className="gap-1.5">
                        <Server className="h-3 w-3" />
                        {nodeName}
                      </Badge>
                    )}
                    <Badge variant="secondary">{schema.length} параметров</Badge>
                    <Badge variant="default">{enabledFlags} вкл.</Badge>
                    {dirty && (
                      <Badge
                        variant="outline"
                        className="border-amber-500/50 text-amber-700 dark:text-amber-300"
                      >
                        {dirtyKeys.length} несохранённых
                      </Badge>
                    )}
                    {needsApply && !dirty && (
                      <Badge
                        variant="outline"
                        className="border-amber-500/50 text-amber-700 dark:text-amber-300"
                      >
                        ждёт doall.sh
                      </Badge>
                    )}
                  </>
                }
                description={
                  <>
                    Параметры файла{" "}
                    <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                      setup
                    </span>{" "}
                    на активном узле
                  </>
                }
                docsHref={DOCS.antizapretConfig}
                actions={
                  <>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      className="w-full sm:w-auto"
                      onClick={() => void load()}
                      disabled={controlsDisabled}
                    >
                      <RefreshCw className="mr-1.5 h-4 w-4" />
                      Обновить
                    </Button>
                    {dirty && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="w-full sm:w-auto"
                        onClick={resetDraft}
                        disabled={controlsDisabled}
                      >
                        Сбросить
                      </Button>
                    )}
                  </>
                }
              />

              <ConfigWorkflowSteps dirty={dirty} pendingApply={pendingApply} />
            </div>
          </div>

          {(dirty || needsApply) && (
            <div
              className={cn(
                "sticky top-14 z-30 flex flex-col gap-3 rounded-lg border px-4 py-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/90 sm:flex-row sm:items-center sm:justify-between",
                dirty
                  ? "border-amber-500/30 bg-amber-500/5"
                  : "border-amber-500/30 bg-background/95",
              )}
            >
              <p className="w-full text-sm sm:min-w-0 sm:flex-1">
                {dirty ? (
                  <>
                    Есть несохранённые изменения ({dirtyKeys.length}). Сохраните
                    перед применением.
                  </>
                ) : (
                  <>Настройки сохранены — осталось выполнить doall.sh на узле.</>
                )}
              </p>
              <div className="flex w-full min-w-0 flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap">
                {dirty ? (
                  <Button
                    type="button"
                    size="sm"
                    className="w-full sm:w-auto"
                    onClick={() => void save()}
                    disabled={controlsDisabled}
                  >
                    <Save className="mr-1.5 h-4 w-4" />
                    Сохранить
                  </Button>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    className="w-full sm:w-auto"
                    onClick={() => setApplyOpen(true)}
                    disabled={controlsDisabled}
                  >
                    <Play className="mr-1.5 h-4 w-4" />
                    Применить doall.sh
                  </Button>
                )}
              </div>
            </div>
          )}

          {backupTcpPortConflict && (
            <SettingsAlert
              variant="warning"
              title="Конфликт OPENVPN_BACKUP_TCP с портом 443"
            >
              Резервные TCP-порты OpenVPN включают <strong>443</strong>, а панель
              публикует HTTPS на этом же порту. Смените «Публичный порт HTTPS» в{" "}
              <Link
                to="/settings/vpn_network"
                className="font-medium text-primary underline-offset-4 hover:underline"
              >
                Настройки → Адрес сайта и HTTPS
              </Link>{" "}
              перед применением doall.sh, иначе панель станет недоступна.
            </SettingsAlert>
          )}

          <div className="grid gap-5 lg:grid-cols-2 lg:items-stretch">
            {FIELD_LAYOUT.map((row, index) => (
              <Fragment key={`layout-row-${index}`}>
                <div className="min-w-0">
                  {row.left ? renderSection(row.left) : null}
                </div>
                <div className="min-w-0">
                  {row.right ? renderSection(row.right) : null}
                </div>
              </Fragment>
            ))}
          </div>

          <div className="mt-5 space-y-5">
            {LAYOUT_BOTTOM.map((title) => renderSection(title))}
            {extraSections.map((section) => (
              <ConfigSectionCard
                key={section.title}
                section={section}
                draft={draft}
                dirtySet={dirtySet}
                disabled={controlsDisabled}
                onDraftChange={handleDraftChange}
              />
            ))}
          </div>
        </>
      )}

      <ConfirmDialogHost dialogProps={dialogProps} />
      <ConfirmDialog
        open={applyOpen}
        onOpenChange={setApplyOpen}
        title="Применить конфигурацию AntiZapret?"
        description="Будет выполнен doall.sh на активном узле. Это может занять несколько минут и перезагрузить правила маршрутизации."
        confirmLabel="Выполнить doall.sh"
        destructive
        loading={applying}
        onConfirm={() => void apply()}
        alert={{
          variant: "warning",
          title: "Длительная операция",
          children: "Не закрывайте вкладку до завершения doall.sh.",
        }}
      />
    </div>
  );
}
