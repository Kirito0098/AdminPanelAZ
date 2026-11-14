import { Bell, Clock, Mail, Network, Server, Shield } from 'lucide-react'
import type { NotificationCategory } from '@/api/notifications'
import type { NotificationTabKey } from '@/context/NotificationCenterContext'

export const CATEGORY_LABEL: Record<NotificationTabKey, string> = {
  all: 'Все',
  requests: 'Заявки',
  security: 'Безопасность',
  nodes: 'Серверы',
  services: 'Сервисы и сеть',
  tasks: 'Задачи',
}

export const CATEGORY_ICON: Record<NotificationTabKey, typeof Bell> = {
  all: Bell,
  requests: Clock,
  security: Shield,
  nodes: Server,
  services: Network,
  tasks: Mail,
}

export function categoryLabel(category: NotificationCategory): string {
  return CATEGORY_LABEL[category] ?? category
}
