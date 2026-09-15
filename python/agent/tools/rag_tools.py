# -*- coding: utf-8 -*-
"""
知识库（RAG）工具层：暴露给 Agent 的 @tool 集合。

语义搜索从向量知识库检索文档分块，返回人类可读文本供 LLM 阅读。
"""

from langchain.tools import tool

from agent.rag.rag_service import get_rag_service


@tool(description="从知识库中搜索")
def search_from_kb(kb_ids: list[str] | str, query: str, k: int = 4) -> str:
    """从知识库中按语义检索相关内容，返回命中的文档分块。

    触发场景：主人询问知识库中的问题，如"查一下我们公司/某知识库里的 XX 内容"时调用。

    参数说明：
    - kb_ids: 知识库 ID 列表（如 ["kb-xxx", "kb-yyy"]）或单个 ID（字符串）；
      传 "all" 表示在所有知识库中搜索。
    - query: 查询文本（必填）。
    - k: 返回的文档分块数量（默认 4）。

    返回命中的分块内容，每块附带来源（源文件名或文档 ID）；
    未命中时返回提示，可尝试换一种问法或调整关键词后重试。
    """
    rag_service = get_rag_service()

    # 构造 Chroma where 过滤条件：单 ID 用等值，多 ID 用 $in，"all" 不过滤
    if kb_ids == "all":
        where = None
    elif isinstance(kb_ids, str):
        where = {"kb_id": kb_ids}
    else:
        where = {"kb_id": {"$in": list(kb_ids)}}

    try:
        results = rag_service.search_sync(query=query, k=k, filter=where)
    except Exception as e:
        return f"知识库搜索失败：{e}"

    if not results:
        return "知识库中没有找到相关内容，可以换一种问法或添加文档后再试。"

    lines = [f"已从知识库中找到 {len(results)} 条相关内容："]
    for i, doc in enumerate(results, 1):
        meta = doc.metadata or {}
        source = (
            meta.get("source")
            or meta.get("doc_id")
            or getattr(doc, "id", None)
            or "未知来源"
        )
        content = (doc.page_content or "").strip()
        lines.append(f"\n[{i}] 来源：{source}\n{content}")

    return "\n".join(lines)
