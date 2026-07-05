import { Check, FileKey } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  profileRouteForFile,
  profileRouteHint,
  profileRouteLabel,
  splitProfileFilesByRoute,
  type ProfileRoute,
} from '@/tg-mini/lib/profileFiles'
import type { TgMiniConfigFile } from '@/types'
import { useEffect, useMemo, useState } from 'react'

function fileLabel(file: TgMiniConfigFile): string {
  return file.download_filename || file.filename || file.path
}

function fileExtension(file: TgMiniConfigFile): string {
  const name = fileLabel(file)
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toUpperCase() : 'CFG'
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
  }, [files, selectedPath])

  const routeFiles = route === 'antizapret' ? antizapret : vpn

  const handleRouteChange = (nextRoute: ProfileRoute) => {
    setRoute(nextRoute)
    const nextFiles = nextRoute === 'antizapret' ? antizapret : vpn
    if (nextFiles.length > 0) {
      onSelectedPathChange(nextFiles[0].path)
    }
  }

  if (files.length === 0) {
    return (
      <div className="tg-mini-empty-inline">
        <FileKey size={20} className="text-muted-foreground" aria-hidden />
        <p>Файлы профиля не найдены на узле</p>
      </div>
    )
  }

  return (
    <div className="tg-mini-profile-picker">
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
                className={cn('tg-mini-segment tg-mini-segment--stacked', active && 'is-active')}
                onClick={() => handleRouteChange(option)}
              >
                <span className="tg-mini-segment-title">{profileRouteLabel(option)}</span>
                <span className="tg-mini-segment-sub">{profileRouteHint(option)}</span>
                <span className="tg-mini-segment-count">{count}</span>
              </button>
            )
          })}
        </div>
      ) : (
        <p className="tg-mini-route-hint">{profileRouteHint(route)}</p>
      )}

      <div className="tg-mini-file-list" role="listbox" aria-label="Файлы профиля">
        {routeFiles.map((file) => {
          const active = file.path === selectedPath
          return (
            <button
              key={file.path}
              type="button"
              role="option"
              aria-selected={active}
              className={cn('tg-mini-file-option', active && 'is-active')}
              onClick={() => onSelectedPathChange(file.path)}
            >
              <span className="tg-mini-file-option-ext" aria-hidden>
                {fileExtension(file)}
              </span>
              <span className="tg-mini-file-option-body">
                <span className="tg-mini-file-option-name">{fileLabel(file)}</span>
                {!showRouteTabs && (
                  <span className="tg-mini-file-option-meta">{profileRouteLabel(route)}</span>
                )}
              </span>
              {active && <Check size={18} className="tg-mini-file-option-check" aria-hidden />}
            </button>
          )
        })}
      </div>
    </div>
  )
}
