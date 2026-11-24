import { ApiError, rebuildPanel } from "@/api/client";
import SettingsAlert from "@/components/settings/SettingsAlert";
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from "@/components/settings/SettingsCard";
import { SettingsDangerZone } from "@/components/settings/SettingsChrome";
import {
  UPDATE_CONFIRM_DURATION_NOTICE,
  UPDATE_LONG_RUNNING_NOTICE,
  UPDATE_POLL_BUSY_ALERT_BODY,
  UPDATE_POLL_BUSY_ALERT_TITLE,
  isLikelyBuildBusyPollError,
  resolveUpdateTaskErrorMessage,
} from "@/components/settings/updateGuidance";
import { ConfirmDialogHost } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { useNotifications } from "@/context/NotificationContext";
import { useProgress } from "@/context/ProgressContext";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";
import { Hammer, Rocket, Server } from "lucide-react";
import { useState } from "react";

const REBUILD_STEPS = [
  { icon: Hammer, label: "Готовая сборка", detail: "загрузка из GitHub без npm" },
  { icon: Server, label: "Перезапуск", detail: "adminpanelaz через systemd" },
] as const;

type Props = {
  className?: string;
};

export default function PanelRebuildCard({ className }: Props) {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications();
  const { trackBackgroundTask } = useProgress();
  const { confirm, dialogProps } = useConfirmDialog();
  const [rebuilding, setRebuilding] = useState(false);

  const handleRebuild = () => {
    confirm({
      title: "Переустановить интерфейс и перезапустить?",
      description:
        "Загрузит готовую сборку интерфейса из GitHub и перезапустит сервис панели. Если сборки для текущего коммита нет, интерфейс будет собран на сервере (npm run build:all).",
      alert: {
        variant: "warning",
        title: "Панель будет недоступна",
        children: (
          <>
            Сервис перезапустится сразу после переустановки. Не запускайте одновременно
            с обновлением из Git.
            <br />
            <br />
            {UPDATE_CONFIRM_DURATION_NOTICE}
          </>
        ),
      },
      confirmLabel: "Переустановить и перезапустить",
      destructive: true,
      onConfirm: async () => {
        setRebuilding(true);
        try {
          const resp = await rebuildPanel();
          trackBackgroundTask(resp.task_id, {
            onComplete: () => {
              success(
                resp.message || "Интерфейс переустановлен, панель перезапускается",
              );
            },
            onError: (task, message) => {
              const resolved = resolveUpdateTaskErrorMessage(message, task);
              if (isLikelyBuildBusyPollError(message, task)) {
                notifyWarning(resolved);
                return;
              }
              notifyError(resolved);
            },
          });
        } catch (err) {
          notifyError(
            err instanceof ApiError ? err.message : "Ошибка переустановки интерфейса",
          );
        } finally {
          setRebuilding(false);
        }
      },
    });
  };

  return (
    <div className={className}>
      <ConfirmDialogHost dialogProps={dialogProps} />
      <Card>
        <CardHeader>
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Rocket size={16} aria-hidden />
            </span>
            <div className="min-w-0">
              <CardTitle>Переустановка интерфейса</CardTitle>
              <CardDescription className="mt-1">
                Переустановка frontend и mini-app без обновления кода из Git: готовая
                сборка из GitHub, а если её для текущего коммита нет —{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-[11px]">
                  {"npm run build:all"}
                </code>{" "}
                на сервере.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            {REBUILD_STEPS.map((step) => (
              <div
                key={step.label}
                className="flex items-start gap-3 rounded-lg border bg-muted/15 p-3 text-sm"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <step.icon size={16} aria-hidden />
                </div>
                <div>
                  <p className="font-medium">{step.label}</p>
                  <p className="text-xs text-muted-foreground">{step.detail}</p>
                </div>
              </div>
            ))}
          </div>
          <SettingsAlert variant="info" title="Длительность переустановки">
            {UPDATE_LONG_RUNNING_NOTICE}
          </SettingsAlert>
          <SettingsAlert variant="info" title={UPDATE_POLL_BUSY_ALERT_TITLE}>
            {UPDATE_POLL_BUSY_ALERT_BODY}
          </SettingsAlert>
          <SettingsAlert variant="info" title="Когда использовать">
            Если UI не обновился после обновления или деплоя: переустановка заново
            ставит готовую сборку для текущего коммита.
          </SettingsAlert>
          <SettingsDangerZone
            title="Переустановить и перезапустить"
            description="Сервис перезапустится после переустановки — дождитесь завершения процесса, не запускайте обновление параллельно."
          >
            <Button
              type="button"
              variant="destructive"
              className="gap-2"
              disabled={rebuilding}
              onClick={handleRebuild}
            >
              <Hammer size={16} />
              {rebuilding ? "Запуск..." : "Переустановить и перезапустить"}
            </Button>
          </SettingsDangerZone>
        </CardContent>
      </Card>
    </div>
  );
}
