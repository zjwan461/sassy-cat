/**
 * 解析 present 工具的结构化结果，供聊天消息渲染文件卡片。
 *
 * 工具返回形如：
 * { type: 'present', title, summary, files: [...], totalAdded, totalRemoved }
 */
export function extractPresentation(tools) {
  if (!Array.isArray(tools)) return null
  for (let i = tools.length - 1; i >= 0; i -= 1) {
    const t = tools[i]
    if (!t || t.name !== 'present' || !t.result) continue
    try {
      const parsed = typeof t.result === 'string' ? JSON.parse(t.result) : t.result
      if (!parsed || parsed.type !== 'present' || !Array.isArray(parsed.files) || !parsed.files.length) continue
      return normalize(parsed)
    } catch {
      // 工具结果被截断/不是 JSON 时忽略，保留原始工具步骤展示
    }
  }
  return null
}

function normalize(raw) {
  const files = raw.files
    .filter((f) => f && f.name)
    .map((f) => ({
      name: String(f.name),
      path: String(f.path || f.name),
      absolute: String(f.absolute || ''),
      ext: String(f.ext || ''),
      size: Number(f.size) || 0,
      lines: Number(f.lines) || 0,
      change: f.change || 'unknown',
      added: Number.isFinite(Number(f.added)) && f.added !== null ? Number(f.added) : null,
      removed: Number.isFinite(Number(f.removed)) && f.removed !== null ? Number(f.removed) : null,
    }))

  return {
    title: raw.title || `本轮产出 ${files.length} 个文件`,
    summary: raw.summary || '',
    files,
    totalAdded: Number(raw.totalAdded) || 0,
    totalRemoved: Number(raw.totalRemoved) || 0,
    hasDiff: files.some((f) => f.added !== null || f.removed !== null),
  }
}
