import { FormEvent, useEffect, useState } from 'react'
import { Check, HeartPulse, Pencil, Plus, Server, Trash2 } from 'lucide-react'
import { ApiError, checkNodeHealth, createNode, deleteNode, getNodes, updateNode } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { Node, NodeStatus } from '@/types'
import { Navigate } from 'react-router-dom'

const statusLabels: Record<NodeStatus, string> = {
  online: 'Онлайн',
  offline: 'Офлайн',
  unknown: 'Неизвестно',
}

const statusVariant: Record<NodeStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  online: 'default',
  offline: 'destructive',
  unknown: 'secondary',
}

export default function NodesPage() {
  const { user } = useAuth()
  const { activeNode, refresh, refreshNodes, activate } = useNode()
  const { success, error: notifyError } = useNotifications()
  const [nodes, setNodes] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)
  const [showDialog, setShowDialog] = useState(false)
  const [editing, setEditing] = useState<Node | null>(null)
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState(9100)
  const [apiKey, setApiKey] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [healthLoading, setHealthLoading] = useState<number | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      setNodes(await getNodes())
      await refreshNodes()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки узлов')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (user?.role === 'admin') load()
  }, [user?.role])

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  const openCreate = () => {
    setEditing(null)
    setName('')
    setHost('')
    setPort(9100)
    setApiKey('')
    setShowDialog(true)
  }

  const openEdit = (node: Node) => {
    setEditing(node)
    setName(node.name)
    setHost(node.host)
    setPort(node.port)
    setApiKey('')
    setShowDialog(true)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      if (editing) {
        const payload: Record<string, string | number> = { name, host, port }
        if (apiKey) payload.api_key = apiKey
        await updateNode(editing.id, payload)
        success('Узел обновлён')
      } else {
        if (!apiKey) {
          notifyError('API-ключ обязателен')
          return
        }
        await createNode({ name, host, port, api_key: apiKey })
        success('Узел добавлен')
      }
      setShowDialog(false)
      await load()
      await refresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (node: Node) => {
    if (!confirm(`Удалить узел «${node.name}»?`)) return
    try {
      await deleteNode(node.id)
      success('Узел удалён')
      await load()
      await refresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    }
  }

  const handleHealth = async (node: Node) => {
    setHealthLoading(node.id)
    try {
      const result = await checkNodeHealth(node.id)
      const label = statusLabels[result.status] ?? result.status
      if (result.status === 'online') {
        success(`Узел «${node.name}»: ${label}`)
      } else {
        notifyError(`Узел «${node.name}»: ${label}`)
      }
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки')
    } finally {
      setHealthLoading(null)
    }
  }

  const handleActivate = async (node: Node) => {
    try {
      await activate(node.id)
      success(`Активный узел: ${node.name}`)
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка активации')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Server size={24} />
            Узлы
          </h2>
          <p className="text-sm text-muted-foreground">
            Управление VPN-серверами AntiZapret (Controller → Nodes)
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus size={16} />
          Добавить узел
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Список узлов</CardTitle>
          <CardDescription>
            Активный узел: {activeNode?.name ?? '—'}. Все операции выполняются на активном узле.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Загрузка...</p>
          ) : nodes.length === 0 ? (
            <p className="text-sm text-muted-foreground">Узлы не найдены</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Имя</TableHead>
                  <TableHead>Адрес</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead className="text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {nodes.map((node) => {
                  const isActive = activeNode?.id === node.id
                  return (
                    <TableRow key={node.id} className={cn(isActive && 'bg-muted/40')}>
                      <TableCell className="font-medium">
                        {node.name}
                        {isActive && (
                          <Badge variant="outline" className="ml-2 text-[10px]">
                            активный
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="mono text-xs">
                        {node.is_local ? 'local' : `${node.host}:${node.port}`}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant[node.status]}>{statusLabels[node.status]}</Badge>
                      </TableCell>
                      <TableCell>
                        {node.is_local ? (
                          <Badge variant="secondary">Локальный</Badge>
                        ) : (
                          <Badge variant="outline">Удалённый</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          {!isActive && (
                            <Button
                              variant="ghost"
                              size="icon"
                              title="Активировать"
                              onClick={() => handleActivate(node)}
                            >
                              <Check size={16} />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Проверка здоровья"
                            disabled={healthLoading === node.id}
                            onClick={() => handleHealth(node)}
                          >
                            <HeartPulse size={16} />
                          </Button>
                          {!node.is_local && (
                            <>
                              <Button
                                variant="ghost"
                                size="icon"
                                title="Редактировать"
                                onClick={() => openEdit(node)}
                              >
                                <Pencil size={16} />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                title="Удалить"
                                className="text-destructive"
                                onClick={() => handleDelete(node)}
                              >
                                <Trash2 size={16} />
                              </Button>
                            </>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent>
          <form onSubmit={handleSubmit}>
            <DialogHeader>
              <DialogTitle>{editing ? 'Редактировать узел' : 'Добавить узел'}</DialogTitle>
              <DialogDescription>
                Удалённый узел должен запускать node agent с тем же API-ключом.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="node-name">Имя</Label>
                <Input id="node-name" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="node-host">Хост</Label>
                <Input
                  id="node-host"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="vpn.example.com"
                  required={!editing?.is_local}
                  disabled={!!editing?.is_local}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="node-port">Порт агента</Label>
                <Input
                  id="node-port"
                  type="number"
                  min={1}
                  max={65535}
                  value={port}
                  onChange={(e) => setPort(Number(e.target.value))}
                  disabled={!!editing?.is_local}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="node-key">API-ключ (X-Node-Key)</Label>
                <Input
                  id="node-key"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={editing ? 'Оставьте пустым, чтобы не менять' : 'Минимум 8 символов'}
                  required={!editing}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowDialog(false)}>
                Отмена
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Сохранение...' : editing ? 'Сохранить' : 'Добавить'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
