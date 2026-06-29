import { FileKey } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import {
  profileRouteForFile,
  profileRouteLabel,
  splitProfileFilesByRoute,
  type ProfileRoute,
} from '@/tg-mini/lib/profileFiles'
import type { TgMiniConfigFile } from '@/types'
import { useEffect, useMemo, useState } from 'react'

function fileLabel(file: TgMiniConfigFile): string {
  return file.download_filename || file.filename || file.path
}

function defaultRoute(files: TgMiniConfigFile[], selectedPath: string): ProfileRoute {
  const selected = files.find((file) => file.path === selectedPath)
  if (selected) return profileRouteForFile(selected)
  const { antizapret, vpn } = splitProfileFilesByRoute(files)
  if (vpn.length > 0) return 'vpn'
  if (antizapret.length > 0) return 'antizapret'
  return 'vpn'
}

interface MiniProfileFilePickerProps {
  files: TgMiniConfigFile[]
  selectedPath: string
  onSelectedPathChange: (path: string) => void
}

export default function MiniProfileFilePicker({
  files,
  selectedPath,
  onSelectedPathChange,
}: MiniProfileFilePickerProps) {
  const { antizapret, vpn } = useMemo(() => splitProfileFilesByRoute(files), [files])
  const showRouteTabs = antizapret.length > 0 && vpn.length > 0
  const [route, setRoute] = useState<ProfileRoute>(() => defaultRoute(files, selectedPath))

  useEffect(() => {
    setRoute(defaultRoute(files, selectedPath))
  }, [files])

  const routeFiles = route === 'antizapret' ? antizapret : vpn

  const handleRouteChange = (nextRoute: ProfileRoute) => {
    setRoute(nextRoute)
    const nextFiles = nextRoute === 'antizapret' ? antizapret : vpn
    if (nextFiles.length > 0) {
      onSelectedPathChange(nextFiles[0].path)
    }
  }

  if (files.length === 0) {
    return <p className="text-sm text-muted-foreground">Файлы профиля не найдены</p>
  }

  return (
    <div className="space-y-2">
      {showRouteTabs ? (
        <div
          className="tg-mini-segmented tg-mini-segmented--cols-2"
          role="tablist"
          aria-label="Тип маршрута"
        >
          {(['antizapret', 'vpn'] as const).map((option) => {
            const count = option === 'antizapret' ? antizapret.length : vpn.length
            const active = route === option
            return (
              <button
                key={option}
                type="button"
                role="tab"
                aria-selected={active}
                className={cn('tg-mini-segment', active && 'is-active')}
                onClick={() => handleRouteChange(option)}
              >
                <span>{profileRouteLabel(option)}</span>
                <span className="tg-mini-segment-count">{count}</span>
              </button>
            )
          })}
        </div>
      ) : (
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {profileRouteLabel(route)}
        </p>
      )}

      {routeFiles.length > 1 ? (
        <Select value={selectedPath} onValueChange={onSelectedPathChange}>
          <SelectTrigger className="h-11 w-full">
            <div className="flex min-w-0 items-center gap-2">
              <FileKey size={16} className="shrink-0 text-muted-foreground" aria-hidden />
              <SelectValue placeholder="Выберите файл профиля" />
            </div>
          </SelectTrigger>
          <SelectContent className="z-[100] max-h-56">
            {routeFiles.map((file) => (
              <SelectItem key={file.path} value={file.path}>
                {fileLabel(file)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <div className="tg-mini-file-chip">
          <FileKey size={16} className="shrink-0 text-primary" aria-hidden />
          <span className="truncate text-sm">{fileLabel(routeFiles[0])}</span>
        </div>
      )}
    </div>
  )
}
