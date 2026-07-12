import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVisibleNavGroups, type SettingsSection } from '@/components/settings/SettingsNav'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'

type MobileSettingsSectionPickerProps = {
  value: SettingsSection
}

/**
 * Mobile-only settings section switcher (<lg). Reuses sidebar visibility via getVisibleNavGroups.
 */
export default function MobileSettingsSectionPicker({ value }: MobileSettingsSectionPickerProps) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { isSettingsTabEnabled, isEnabled } = useFeatureModules()
  const isAdmin = user?.role === 'admin'

  const visibleGroups = useMemo(
    () => getVisibleNavGroups(isAdmin, isSettingsTabEnabled, isEnabled),
    [isAdmin, isSettingsTabEnabled, isEnabled],
  )

  const itemCount = visibleGroups.reduce((sum, group) => sum + group.items.length, 0)
  if (itemCount <= 1) return null

  return (
    <div className="lg:hidden orientation-compact-settings-section">
      <Select value={value} onValueChange={(section) => navigate(`/settings/${section}`)}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Раздел настроек" />
        </SelectTrigger>
        <SelectContent>
          {visibleGroups.map((group) => (
            <SelectGroup key={group.label}>
              {visibleGroups.length > 1 ? <SelectLabel>{group.label}</SelectLabel> : null}
              {group.items.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
