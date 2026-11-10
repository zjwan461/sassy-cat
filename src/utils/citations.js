/**
 * 从 search_from_kb 工具结果中提取「参考来源」。
 *
 * rag_tools 的输出格式：
 *   已从知识库中找到 N 条相关内容：
 *   [1] 来源：员工手册.pdf（相关度 0.92 · 混合召回）
 *   分块正文……
 */
export function extractKbCitations(tools) {
  if (!Array.isArray(tools)) return []
  const hits = []

  for (const tool of tools) {
    if (!tool || tool.name !== 'search_from_kb' || !tool.result) continue
    const text = String(tool.result)
    const re = /\[(\d+)\]\s*来源：([^\n（]+?)(?:（[^）]*）)?\s*\n([\s\S]*?)(?=\n\[\d+\]\s*来源：|$)/g
    let match
    while ((match = re.exec(text)) !== null) {
      const index = Number(match[1])
      const source = match[2].trim()
      const content = match[3].trim()
      if (!index || !source || !content) continue
      hits.push({ index, source, content })
    }
  }

  // 多次检索时保留每个序号的最新一条，并按序号排序
  const byIndex = new Map()
  for (const hit of hits) {
    if (!hit.content) continue
    byIndex.set(hit.index, hit)
  }
  return [...byIndex.values()].sort((a, b) => a.index - b.index)
}
