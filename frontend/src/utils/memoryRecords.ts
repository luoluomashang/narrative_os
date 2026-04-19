import type { MemoryRecord } from '@/types/api'

export interface MemorySourceLink {
  label: string
  hint: string
  to: string
}

function toStringValue(value: unknown): string {
  if (typeof value === 'string') {
    return value.trim()
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }

  if (Array.isArray(value)) {
    return value
      .map((entry) => toStringValue(entry))
      .filter(Boolean)
      .join(' / ')
  }

  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .slice(0, 4)
      .map(([key, entry]) => `${key}: ${toStringValue(entry)}`)
      .join(' / ')
  }

  return ''
}

function firstString(meta: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = toStringValue(meta[key])
    if (value) {
      return value
    }
  }

  return ''
}

function firstNumber(meta: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = meta[key]
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }

    if (typeof value === 'string') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }
  }

  return null
}

export function formatMemoryMetadata(meta: Record<string, unknown>, limit = 4): string[] {
  return Object.entries(meta ?? {})
    .slice(0, limit)
    .map(([key, value]) => `${key}: ${toStringValue(value)}`)
    .filter(Boolean)
}

export function buildMemoryMetadataItems(record: MemoryRecord | null, limit = 12) {
  if (!record) {
    return []
  }

  return Object.entries(record.metadata ?? {})
    .slice(0, limit)
    .map(([key, value]) => ({
      label: key,
      value: toStringValue(value) || '未提供',
    }))
}

export function describeMemorySource(record: MemoryRecord): string {
  const meta = record.metadata ?? {}
  const chapter = firstNumber(meta, ['chapter', 'chapter_id', 'chapter_number', 'chapter_index'])
  if (chapter !== null) {
    return `章节 ${chapter}`
  }

  const character = firstString(meta, ['character_name', 'character', 'speaker', 'actor'])
  if (character) {
    return `角色 ${character}`
  }

  const session = firstString(meta, ['session_id', 'session', 'turn_id'])
  if (session) {
    return `会话 ${session}`
  }

  const worldEntity = firstString(meta, ['region', 'region_name', 'faction', 'faction_name', 'world_entity'])
  if (worldEntity) {
    return `世界设定 ${worldEntity}`
  }

  return '暂未识别来源'
}

export function resolveMemorySourceLink(projectId: string, record: MemoryRecord): MemorySourceLink | null {
  const meta = record.metadata ?? {}
  const chapter = firstNumber(meta, ['chapter', 'chapter_id', 'chapter_number', 'chapter_index'])
  if (chapter !== null) {
    return {
      label: `跳转到第 ${chapter} 章`,
      hint: '定位到章节写作工作台，继续核对上下文和原文。',
      to: `/project/${projectId}/write?chapter=${chapter}`,
    }
  }

  const character = firstString(meta, ['character_name', 'character', 'speaker', 'actor'])
  if (character) {
    return {
      label: `打开角色 ${character}`,
      hint: '进入角色矩阵并按名称定位，继续核对人物状态。',
      to: `/project/${projectId}/characters?name=${encodeURIComponent(character)}`,
    }
  }

  const session = firstString(meta, ['session_id', 'session', 'turn_id'])
  if (session) {
    return {
      label: '打开 TRPG 会话',
      hint: '该条记忆更接近会话轨迹，可回到 TRPG 页面继续检查。',
      to: `/project/${projectId}/trpg`,
    }
  }

  const worldEntity = firstString(meta, ['region', 'region_name', 'faction', 'faction_name', 'world_entity'])
  if (worldEntity) {
    return {
      label: '打开世界构建',
      hint: `该条记忆更接近世界设定实体“${worldEntity}”，建议回到世界构建继续核对。`,
      to: `/project/${projectId}/worldbuilder`,
    }
  }

  const sourcePage = firstString(meta, ['source_page', 'origin', 'page'])
  if (sourcePage.includes('metric') || sourcePage.includes('quality')) {
    return {
      label: '打开质量仪表盘',
      hint: '该条记录来自质量或评测上下文，可回到质量仪表盘继续核对。',
      to: `/project/${projectId}/metrics`,
    }
  }

  return null
}