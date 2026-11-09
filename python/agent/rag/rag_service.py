"""
RAG 服务：文档分块、写入知识库、语义查询
"""

from typing import List, Optional, Dict, Any
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
    HTMLHeaderTextSplitter,
    LatexTextSplitter,
    RecursiveJsonSplitter,
    Language,
)
from langchain_core.documents import Document
from uuid import uuid4
import json
import os
import re
import torch

import paths
import config_loader
from agent.rag.hybrid import BM25Index, rrf_fuse


class RAGService:
    """RAG 服务类，封装文档处理和向量存储功能。
    
    支持配置热重载：每次使用时自动检测 embedding 配置是否变化，
    若变化则重新初始化 embedding 模型和向量存储。
    """
    
    def __init__(
        self,
        collection_name: str = "sassy-kb",
    ):
        """
        初始化 RAG 服务
        
        Args:
            collection_name: Chroma 集合名称
        """
        self.collection_name = collection_name
        
        # 记录上一次 embedding 配置指纹，用于检测配置变化
        self._last_embedding_fingerprint: str | None = None
        
        # 初始化 embedding 模型和向量存储
        self.embeddings = None
        self.vector_store = None
        # 关键词检索缓存：{where 指纹: (collection count, BM25Index, {chunk_id: Document})}
        # 只在写入/删除/编辑后失效，查询时按 count 兜底检测外部变更
        self._keyword_cache: dict[str, tuple[int, BM25Index, dict[str, Document]]] = {}
        self._ensure_embeddings()
    
    def _get_embedding_fingerprint(self) -> str:
        """获取当前 embedding 配置指纹，用于检测配置是否变化"""
        cfg = config_loader.current()
        rag_cfg = cfg.get("rag.embeddingModel", {}) or {}
        # 用 type + model + localPath + baseUrl + apiKey 组合为指纹
        parts = [
            str(rag_cfg.get("type", "local")),
            str(rag_cfg.get("model", "")),
            str(rag_cfg.get("localPath", "")),
            str(rag_cfg.get("baseUrl", "")),
            str(rag_cfg.get("apiKey", "")),
        ]
        return "|".join(parts)
    
    def _init_embeddings(self):
        """根据当前配置初始化 embedding 模型"""
        cfg = config_loader.current()
        emb_cfg = cfg.get("rag.embeddingModel", {}) or {}
        emb_type = emb_cfg.get("type", "local")
        
        if emb_type == "local":
            # 优先使用「智能下载」写入配置的本地模型目录（离线秒加载，不走网络）；
            # 未下载时回退为 HuggingFace 仓库名（首次使用会触发在线下载）
            local_path = emb_cfg.get("localPath") or ""
            model_name = local_path or emb_cfg.get("model", "BAAI/bge-small-zh-v1.5")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model_kwargs = {"device": device, "trust_remote_code": True}
            encode_kwargs = {"normalize_embeddings": True}
            
            return HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs=model_kwargs,
                encode_kwargs=encode_kwargs,
            )
        else:
            return OpenAIEmbeddings(
                base_url=emb_cfg.get("baseUrl", ""),
                api_key=emb_cfg.get("apiKey", ""),
                model=emb_cfg.get("model", ""),
                check_embedding_ctx_length=False,
            )
    
    def _init_vector_store(self) -> Chroma:
        """初始化 Chroma 向量存储"""
        chroma_dir = paths.data_dir() + "/chroma"
        return Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=chroma_dir,
        )
    
    def _ensure_embeddings(self):
        """确保 embedding 模型和向量存储与当前配置一致。
        若检测到配置变化，自动重新初始化。
        """
        fingerprint = self._get_embedding_fingerprint()
        if self.embeddings is not None and fingerprint == self._last_embedding_fingerprint:
            return  # 配置未变，无需重建
        
        self.embeddings = self._init_embeddings()
        self.vector_store = self._init_vector_store()
        self._last_embedding_fingerprint = fingerprint
        # embedding 变更后集合/分块可能整体换了维度，关键词索引一并作废
        self._invalidate_keyword_cache()

    def _invalidate_keyword_cache(self) -> None:
        """写入/删除/编辑后清空 BM25 缓存；下次查询按需重建。"""
        self._keyword_cache.clear()

    def _get_retrieval_config(self) -> dict:
        cfg = config_loader.current()
        return cfg.get("rag.retrieval", {}) or {}

    def _keyword_index(
        self, where: dict | None
    ) -> tuple[BM25Index, dict[str, Document]]:
        """按 metadata 过滤条件构建（或复用）BM25 索引。

        Chroma 没有内置 BM25，这里把过滤后的分块一次性拉到内存建索引；
        桌面知识库规模下开销可接受，且用 count + 写入失效双重校验缓存。
        """
        key = json.dumps(where, sort_keys=True, ensure_ascii=False) if where else "__all__"
        try:
            count = int(self.vector_store._collection.count())
        except Exception:
            count = -1

        cached = self._keyword_cache.get(key)
        if cached and cached[0] == count:
            return cached[1], cached[2]

        data = self.vector_store._collection.get(
            where=where, include=["documents", "metadatas"]
        )
        ids = data.get("ids") or []
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []

        docs_by_id: dict[str, Document] = {}
        pairs: list[tuple[str, str]] = []
        for i, chunk_id in enumerate(ids):
            text = documents[i] if i < len(documents) else ""
            if not text or not text.strip():
                continue
            meta = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
            docs_by_id[chunk_id] = Document(page_content=text, metadata=meta, id=chunk_id)
            pairs.append((chunk_id, text))

        index = BM25Index(pairs)
        # 简单容量控制：最多缓存 8 个过滤维度（all / 每个 kb / 每个 doc）
        if len(self._keyword_cache) >= 8:
            self._keyword_cache.clear()
        self._keyword_cache[key] = (count, index, docs_by_id)
        return index, docs_by_id

    def _vector_ranked_ids(
        self, query: str, limit: int, where: dict | None
    ) -> list[str]:
        """向量召回，返回按相似度排序的 chunk id（只关心名次，供 RRF 融合）。"""
        embedding = self.embeddings.embed_query(query)
        result = self.vector_store._collection.query(
            query_embeddings=[embedding],
            n_results=max(1, limit),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        return [str(i) for i in ids]

    def search_hits(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, str] | None = None,
        hybrid: bool | None = None,
    ) -> List[dict]:
        """检索并返回带分数/来源方式的结果，供 UI 与工具层共用。

        默认走混合检索（向量 + BM25，RRF 融合）；`rag.retrieval.hybrid=false`
        或显式传 hybrid=False 时退化为纯向量。返回的 score 是归一化后的融合分
        （最高为 1.0），只用于排序/展示，不是概率。
        """
        self._ensure_embeddings()
        query = (query or "").strip()
        if not query:
            return []

        params = self._get_retrieval_config()
        if hybrid is None:
            hybrid = bool(params.get("hybrid", True))
        multiplier = params.get("candidateMultiplier", 4)
        try:
            multiplier = min(10, max(1, int(multiplier)))
        except (TypeError, ValueError):
            multiplier = 4
        candidate_k = max(k * multiplier, k + 10)

        vector_ids: list[str] = []
        try:
            vector_ids = self._vector_ranked_ids(query, candidate_k, filter)
        except Exception as e:
            # 向量侧失败（embedding 服务抖动、集合维度与当前模型不一致等）时
            # 仍可依赖 BM25 关键词结果，保证知识库检索不至于整个不可用。
            import logging

            logging.getLogger(__name__).warning("向量召回失败，降级为关键词检索: %s", e)

        keyword_ids: list[str] = []
        docs_by_id: dict[str, Document] = {}
        if hybrid:
            index, docs_by_id = self._keyword_index(filter)
            keyword_ids = [chunk_id for chunk_id, _ in index.search(query, candidate_k)]

        if not vector_ids and not keyword_ids:
            return []

        if hybrid and keyword_ids:
            fused = rrf_fuse([vector_ids, keyword_ids])
        else:
            # 纯向量：名次分同样用 RRF 的 1/(60+rank)，保持分数尺度一致
            fused = {chunk_id: 1.0 / (60 + rank) for rank, chunk_id in enumerate(vector_ids, 1)}

        vector_rank = {chunk_id: rank for rank, chunk_id in enumerate(vector_ids, 1)}
        keyword_rank = {chunk_id: rank for rank, chunk_id in enumerate(keyword_ids, 1)}
        ranked = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:k]
        max_score = ranked[0][1] if ranked else 1.0

        # 纯向量模式下没有关键词索引的 docs 映射，按需补齐
        missing = [chunk_id for chunk_id, _ in ranked if chunk_id not in docs_by_id]
        if missing:
            for doc in self.get_by_ids(missing):
                docs_by_id[getattr(doc, "id", None) or ""] = doc

        hits: List[dict] = []
        for chunk_id, score in ranked:
            doc = docs_by_id.get(chunk_id)
            if doc is None:
                continue
            v_rank = vector_rank.get(chunk_id)
            k_rank = keyword_rank.get(chunk_id)
            if v_rank and k_rank:
                match = "hybrid"
            elif k_rank:
                match = "keyword"
            else:
                match = "vector"
            hits.append(
                {
                    "id": chunk_id,
                    "content": doc.page_content,
                    "metadata": doc.metadata or {},
                    "score": round(score / max_score, 4) if max_score else 0.0,
                    "vectorRank": v_rank,
                    "keywordRank": k_rank,
                    "match": match,
                }
            )
        return hits
    
    def refresh(self):
        """强制重新初始化 embedding 模型和向量存储"""
        self._last_embedding_fingerprint = None
        self._ensure_embeddings()
    
    @staticmethod
    def is_markdown(text: str) -> bool:
        """
        判断文本是否为 Markdown 格式
        
        Args:
            text: 输入文本
            
        Returns:
            True=Markdown, False=普通文本
        """
        if not text or len(text) < 3:
            return False
        
        # Markdown 特征正则
        md_patterns = [
            r"^#{1,6}\s+",          # 标题 # ##
            r"^\d+\.\s+",           # 有序列表 1.
            r"^[\-*]\s+",           # 无序列表 - *
            r"\*\*.+?\*\*",         # 加粗 **text**
            r"\*.+?\*",             # 斜体 *text*
            r"\[.+?\]\(.+?\)",      # 链接 [text](url)
            r"!\[.+?\]\(.+?\)",     # 图片 ![](url)
            r"```[\s\S]*?```",      # 代码块
            r"\|.+\|",              # 表格
            r"^\s*---+\s*$",        # 分割线
        ]
        
        score = 0
        for pattern in md_patterns:
            if re.search(pattern, text, re.MULTILINE):
                score += 1
        
        return score >= 2
    
    # 代码文件扩展名 -> langchain 语言（用于按语法分块）
    _CODE_EXT_LANGUAGE: Dict[str, str] = {
        ".py": Language.PYTHON,
        ".pyi": Language.PYTHON,
        ".js": Language.JS,
        ".mjs": Language.JS,
        ".cjs": Language.JS,
        ".jsx": Language.JS,
        ".ts": Language.TS,
        ".tsx": Language.TS,
        ".java": Language.JAVA,
        ".kt": Language.KOTLIN,
        ".kts": Language.KOTLIN,
        ".go": Language.GO,
        ".rs": Language.RUST,
        ".rb": Language.RUBY,
        ".php": Language.PHP,
        ".cs": Language.CSHARP,
        ".c": Language.C,
        ".h": Language.C,
        ".cpp": Language.CPP,
        ".cc": Language.CPP,
        ".hpp": Language.CPP,
        ".scala": Language.SCALA,
        ".swift": Language.SWIFT,
        ".lua": Language.LUA,
        ".pl": Language.PERL,
        ".pm": Language.PERL,
        ".r": Language.R,
        ".hs": Language.HASKELL,
        ".lhs": Language.HASKELL,
        ".ex": Language.ELIXIR,
        ".exs": Language.ELIXIR,
        ".sol": Language.SOL,
        ".rst": Language.RST,
        ".ps1": Language.POWERSHELL,
        ".bat": Language.POWERSHELL,
        ".cmd": Language.POWERSHELL,
    }

    # 文档类扩展名 -> 内容类型（内容无明显特征时的兜底判断）
    _DOC_EXT_CONTENT_TYPE: Dict[str, str] = {
        ".md": "markdown",
        ".markdown": "markdown",
        ".html": "html",
        ".htm": "html",
        ".xhtml": "html",
        ".json": "json",
        ".tex": "latex",
        ".latex": "latex",
    }

    @staticmethod
    def _extract_ext(metadata: Optional[Dict[str, Any]]) -> str:
        """从 metadata 中推断文件扩展名（优先显式 ext，其次 filename/source/name）。"""
        if not metadata:
            return ""
        ext = str(metadata.get("ext") or "").strip().lower()
        if ext:
            return ext if ext.startswith(".") else f".{ext}"
        for key in ("filename", "source", "file_name", "name"):
            value = metadata.get(key)
            if value:
                _, e = os.path.splitext(os.path.basename(str(value)))
                if e:
                    return e.lower()
        return ""

    @staticmethod
    def _looks_like_json(text: str) -> bool:
        """判断文本是否为合法 JSON（对象或数组）。"""
        stripped = text.lstrip()
        if not stripped or stripped[0] not in "[{":
            return False
        try:
            json.loads(text)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        """判断文本是否为 HTML（整体标记或标签密度）。"""
        head = text[:2000].lower()
        if "<!doctype html" in head or "<html" in head or "<body" in head:
            return True
        tag_hits = re.findall(
            r"</?(?:div|p|span|table|thead|tbody|tr|td|th|ul|ol|li|h[1-6]|a|img|"
            r"script|style|section|article|header|footer|nav|pre|code)\b[^>]*>",
            text[:5000],
            re.IGNORECASE,
        )
        return len(tag_hits) >= 5

    @staticmethod
    def _looks_like_latex(text: str) -> bool:
        """判断文本是否为 LaTeX 源码。"""
        return bool(
            re.search(
                r"\\documentclass|\\begin\{|\\section\{|\\subsection\{", text[:3000]
            )
        )

    @classmethod
    def detect_content_type(
        cls,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        识别文档内容类型，用于选择合适的分块器

        Returns:
            'markdown' | 'html' | 'json' | 'latex' | 'code' | 'text'
        """
        text = content or ""
        if not text.strip():
            return "text"

        ext = cls._extract_ext(metadata)

        # 源码文件按代码处理：docling/markitdown 不会产出这些扩展名，
        # 提前判定可避免代码里的 `# 注释` / `- ` 被误识别为 Markdown
        if ext in cls._CODE_EXT_LANGUAGE:
            return "code"

        if cls._looks_like_json(text):
            return "json"
        if cls._looks_like_html(text):
            return "html"
        if cls.is_markdown(text):
            return "markdown"
        if cls._looks_like_latex(text):
            return "latex"

        # 内容无明显特征时，回退到扩展名提示（如几乎不含标记的 .md）
        return cls._DOC_EXT_CONTENT_TYPE.get(ext, "text")

    @staticmethod
    def _recursive(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
        """创建一个通用递归字符分块器。"""
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    @staticmethod
    def _split_markdown(
        content: str,
        doc: Document,
        markdown_headers: Optional[List[tuple]],
        chunk_size: int,
        chunk_overlap: int,
    ) -> List[Document]:
        """Markdown：先按标题层级切分，再用递归分块约束单块大小。"""
        if markdown_headers is None:
            markdown_headers = [("#", "h1"), ("##", "h2"), ("###", "h3")]

        try:
            header_splits = MarkdownHeaderTextSplitter(
                headers_to_split_on=markdown_headers
            ).split_text(content)
        except Exception:
            header_splits = []

        if not header_splits:
            header_splits = [doc]

        # 标题分块只保证语义边界，长章节可能远超 chunk_size，
        # 因此必须再走一次递归分块，避免单块超出 embedding 上下文
        return RAGService._recursive(chunk_size, chunk_overlap).split_documents(
            header_splits
        )

    @staticmethod
    def _pack_small_documents(
        docs: List[Document],
        chunk_size: int,
    ) -> List[Document]:
        """把相邻且 metadata 相同的小分块合并，避免逐元素切分产生大量碎片。

        仅做「向上合并到不超过 chunk_size」，不拆分大块。
        """
        packed: List[Document] = []
        for d in docs:
            if (
                packed
                and packed[-1].metadata == d.metadata
                and len(packed[-1].page_content) + len(d.page_content) + 1 <= chunk_size
            ):
                merged = packed[-1]
                merged.page_content = f"{merged.page_content}\n{d.page_content}"
            else:
                packed.append(
                    Document(page_content=d.page_content, metadata=dict(d.metadata))
                )
        return packed

    @staticmethod
    def _split_html(
        content: str,
        metadata: Dict[str, Any],
        chunk_size: int,
        chunk_overlap: int,
    ) -> List[Document]:
        """HTML：按 h1~h3 标题结构切分，合并小碎片，再用递归分块约束单块大小。"""
        try:
            html_splits = HTMLHeaderTextSplitter(
                headers_to_split_on=[("h1", "h1"), ("h2", "h2"), ("h3", "h3")],
                return_each_element=False,
            ).split_text(content)
        except Exception:
            html_splits = []

        if not html_splits:
            return RAGService._recursive(chunk_size, chunk_overlap).split_documents(
                [Document(page_content=content, metadata=dict(metadata))]
            )

        # HTMLHeaderTextSplitter 会逐元素产出内容，先合并成较大的语义块
        html_splits = RAGService._pack_small_documents(html_splits, chunk_size)
        return RAGService._recursive(chunk_size, chunk_overlap).split_documents(
            html_splits
        )

    @staticmethod
    def _split_json(
        content: str,
        metadata: Dict[str, Any],
        chunk_size: int,
        chunk_overlap: int,
    ) -> List[Document]:
        """JSON：按层级结构切分，保持键值对的语义完整。"""
        try:
            data = json.loads(content)
            splitter = RecursiveJsonSplitter(max_chunk_size=chunk_size)
            return splitter.create_documents(texts=[data])
        except Exception:
            # 非法 JSON 或结构不适配时，退回通用递归分块
            return RAGService._recursive(chunk_size, chunk_overlap).split_documents(
                [Document(page_content=content, metadata=dict(metadata))]
            )

    @classmethod
    def _split_code(
        cls,
        content: str,
        metadata: Dict[str, Any],
        language: Optional[str],
        chunk_size: int,
        chunk_overlap: int,
    ) -> List[Document]:
        """代码：按语言语法（类/函数边界）分块，未知语言退回通用递归分块。"""
        doc = Document(page_content=content, metadata=dict(metadata))
        lang = language or cls._CODE_EXT_LANGUAGE.get(cls._extract_ext(metadata))

        if lang:
            try:
                return RecursiveCharacterTextSplitter.from_language(
                    Language(lang),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                ).split_documents([doc])
            except (ValueError, KeyError):
                pass

        return cls._recursive(chunk_size, chunk_overlap).split_documents([doc])

    @staticmethod
    def _finalize_splits(
        raw_splits: List[Document],
        metadata: Dict[str, Any],
    ) -> List[Document]:
        """统一为分块附加原始 metadata，并过滤空内容。

        合并顺序为「分块自身 metadata <- 调用方 metadata」：既保留分块器
        生成的结构化信息（如 h1/h2 标题层级），又保证调用方 metadata
        （kb_id/doc_id/source 等）不被覆盖。
        """
        all_splits: List[Document] = []
        for split in raw_splits:
            content = split.page_content
            if not content or not content.strip():
                continue
            merged = dict(split.metadata or {})
            merged.update(metadata)
            split.metadata = merged
            all_splits.append(split)
        return all_splits

    def split_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        markdown_headers: Optional[List[tuple]] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        content_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[Document]:
        """
        根据文档类型自动选择合适的分块器进行分块

        支持的内容类型（content_type，为 None 时自动识别）：
            - markdown：MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter
            - html：HTMLHeaderTextSplitter + RecursiveCharacterTextSplitter
            - json：RecursiveJsonSplitter
            - latex：LatexTextSplitter
            - code：RecursiveCharacterTextSplitter.from_language（按语言语法）
            - text：RecursiveCharacterTextSplitter

        Args:
            content: 文档内容
            metadata: 文档元数据（会附加到每个分块）
            markdown_headers: Markdown 标题层级，如 [("#", "h1"), ("##", "h2")]
            chunk_size: 分块块大小
            chunk_overlap: 分块重叠大小
            content_type: 强制指定内容类型；None 时由内容自动识别
            language: 代码分块语言（Language 值，如 "python"），仅 code 类型生效

        Returns:
            分块后的 Document 列表
        """
        if metadata is None:
            metadata = {}

        content = content or ""
        if not content.strip():
            return []

        ctype = content_type or self.detect_content_type(content, metadata)
        doc = Document(page_content=content, metadata=dict(metadata))

        if ctype == "markdown":
            raw_splits = self._split_markdown(
                content, doc, markdown_headers, chunk_size, chunk_overlap
            )
        elif ctype == "html":
            raw_splits = self._split_html(content, metadata, chunk_size, chunk_overlap)
        elif ctype == "json":
            raw_splits = self._split_json(content, metadata, chunk_size, chunk_overlap)
        elif ctype == "latex":
            raw_splits = LatexTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap
            ).split_documents([doc])
        elif ctype == "code":
            raw_splits = self._split_code(
                content, metadata, language, chunk_size, chunk_overlap
            )
        else:
            raw_splits = self._recursive(chunk_size, chunk_overlap).split_documents(
                [doc]
            )

        return self._finalize_splits(raw_splits, metadata)
    
    def add_documents(
        self,
        documents: List[Document],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        添加文档到向量存储
        
        Args:
            documents: 文档列表
            ids: 文档 ID 列表（可选，不指定则自动生成）
            
        Returns:
            文档 ID 列表
        """
        self._ensure_embeddings()  # 确保使用最新的 embedding 配置
        
        if ids is None:
            ids = [str(uuid4()) for _ in range(len(documents))]

        try:
            result = self.vector_store.add_documents(documents, ids=ids)
        except Exception as e:
            text = str(e)
            if "expecting embedding with dimension" in text:
                raise RuntimeError(
                    f"向量维度与现有索引不一致：{text}。"
                    "通常是切换过 Embedding 模型导致：请切回建库时使用的模型，"
                    "或清空该知识库后重新上传文档。"
                ) from e
            raise
        self._invalidate_keyword_cache()
        return result
    
    def save_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        **split_kwargs,
    ) -> List[str]:
        """
        处理并保存文档到向量存储
        
        Args:
            content: 文档内容
            metadata: 文档元数据
            **split_kwargs: 传递给 split_document 的参数
            
        Returns:
            文档 ID 列表
        """
        # 分块
        all_splits = self.split_document(content, metadata, **split_kwargs)
        
        if not all_splits:
            print("警告：文档分块后无有效内容，跳过写入")
            return []
        
        # 保存到向量存储
        ids = [str(uuid4()) for _ in range(len(all_splits))]
        return self.add_documents(all_splits, ids=ids)
    
    async def search(self, query: str, k: int = 4, filter: dict[str, str] | None = None) -> List[Document]:
        """语义搜索（默认混合检索，见 search_hits）"""
        return self.search_sync(query=query, k=k, filter=filter)

    def search_sync(self, query: str, k: int = 4, filter: dict[str, str] | None = None) -> List[Document]:
        """同步检索：返回 Document 列表，保持旧调用方（工具/接口）兼容。"""
        hits = self.search_hits(query=query, k=k, filter=filter)
        return [
            Document(
                page_content=hit["content"],
                metadata=hit.get("metadata") or {},
                id=hit.get("id"),
            )
            for hit in hits
        ]

    # ==================== 删除 ====================

    def delete_by_ids(self, ids: List[str]) -> None:
        """
        按 ID 列表删除文档

        Args:
            ids: 要删除的文档 ID 列表
        """
        self._ensure_embeddings()
        self.vector_store.delete(ids=ids)
        self._invalidate_keyword_cache()

    def delete_by_metadata(self, where: Dict[str, Any]) -> int:
        """
        按 metadata 条件删除文档

        Args:
            where: Chroma where 过滤条件，如 {"source": "test.md"}
                   支持 $eq/$ne/$gt/$gte/$lt/$lte/$in/$nin 等操作符

        Returns:
            删除的文档数量
        """
        self._ensure_embeddings()
        collection = self.vector_store._collection
        # 先查询出匹配的 ID
        results = collection.get(where=where)
        if not results or not results["ids"]:
            return 0
        count = len(results["ids"])
        collection.delete(ids=results["ids"])
        self._invalidate_keyword_cache()
        return count

    def delete_all(self) -> None:
        """清空当前集合中的所有文档"""
        self._ensure_embeddings()
        collection = self.vector_store._collection
        collection.delete()
        self._invalidate_keyword_cache()

    # ==================== 修改 / 更新 ====================

    def update_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        按 ID 更新单个文档的内容和 metadata（不重新分块）

        Args:
            doc_id: 文档 ID
            content: 新内容
            metadata: 新 metadata（可选，不传则保留原 metadata）
        """
        self._ensure_embeddings()
        kwargs: Dict[str, Any] = {"ids": [doc_id], "documents": [content]}
        if metadata is not None:
            kwargs["metadatas"] = [metadata]
        self.vector_store._collection.update(**kwargs)
        self._invalidate_keyword_cache()

    def update_chunk(
        self,
        chunk_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        按分块 ID 更新内容，并**重新 embedding**（内容变化后向量必须同步，
        否则语义检索会命中旧向量）。

        Args:
            chunk_id: 分块（向量）ID
            content: 新内容
            metadata: 新 metadata（可选，不传则保留原 metadata）
        """
        self._ensure_embeddings()
        embedding = self.embeddings.embed_documents([content])[0]
        kwargs: Dict[str, Any] = {
            "ids": [chunk_id],
            "documents": [content],
            "embeddings": [embedding],
        }
        if metadata is not None:
            kwargs["metadatas"] = [metadata]
        self.vector_store._collection.update(**kwargs)
        self._invalidate_keyword_cache()

    def replace_document(
        self,
        where: Dict[str, Any],
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        **split_kwargs,
    ) -> List[str]:
        """
        按 metadata 条件替换文档：先删除旧文档，再重新分块并写入新内容。
        适用于某个来源的文档内容整体变更的场景。

        Args:
            where: 匹配条件，如 {"source": "test.md"}
            content: 新文档内容
            metadata: 新文档的 metadata（可选）
            **split_kwargs: 传递给 split_document 的参数

        Returns:
            新写入的文档 ID 列表
        """
        # 先删除旧文档
        self.delete_by_metadata(where)
        # 再写入新文档
        return self.save_document(content, metadata, **split_kwargs)

    # ==================== 查询（非语义） ====================

    def get_by_ids(self, ids: List[str]) -> List[Document]:
        """
        按 ID 列表获取文档

        Args:
            ids: 文档 ID 列表

        Returns:
            文档列表
        """
        self._ensure_embeddings()
        collection = self.vector_store._collection
        results = collection.get(ids=ids)
        if not results or not results["ids"]:
            return []
        docs = []
        for i, doc_id in enumerate(results["ids"]):
            docs.append(Document(
                page_content=results["documents"][i],
                metadata=results["metadatas"][i] if results.get("metadatas") else {},
                id=doc_id,
            ))
        return docs

    def get_by_metadata(
        self,
        where: Dict[str, Any],
        limit: Optional[int] = None,
    ) -> List[Document]:
        """
        按 metadata 条件查询文档列表（非语义搜索）

        Args:
            where: Chroma where 过滤条件，如 {"source": "test.md"}
            limit: 最大返回数量（None 表示不限制）

        Returns:
            文档列表
        """
        self._ensure_embeddings()
        collection = self.vector_store._collection
        kwargs: Dict[str, Any] = {"where": where}
        if limit is not None:
            kwargs["limit"] = limit
        results = collection.get(**kwargs)
        if not results or not results["ids"]:
            return []
        docs = []
        for i, doc_id in enumerate(results["ids"]):
            docs.append(Document(
                page_content=results["documents"][i],
                metadata=results["metadatas"][i] if results.get("metadatas") else {},
                id=doc_id,
            ))
        return docs

    def get_chunks_page(
        self,
        where: Dict[str, Any],
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[Document], int]:
        """
        按 metadata 条件分页拉取文档分块（非语义搜索，用于流式展示）

        Args:
            where: Chroma where 过滤条件，如 {"kb_id": "xxx"}
            offset: 偏移量
            limit: 每页数量

        Returns:
            (文档分块列表, 满足条件的总数)
        """
        self._ensure_embeddings()
        collection = self.vector_store._collection
        total = len(collection.get(where=where, include=[])["ids"])
        results = collection.get(
            where=where, limit=limit, offset=offset,
            include=["documents", "metadatas"],
        )
        docs: List[Document] = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"]):
                docs.append(Document(
                    page_content=results["documents"][i],
                    metadata=results["metadatas"][i] if results.get("metadatas") else {},
                    id=doc_id,
                ))
        return docs, total

    def count(self) -> int:
        """返回当前集合中的文档总数"""
        self._ensure_embeddings()
        return self.vector_store._collection.count()


# 全局单例（可选，方便快速使用）
_rag_service: Optional[RAGService] = None


def get_rag_service(**kwargs) -> RAGService:
    """获取或创建 RAG 服务单例"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService(**kwargs)
    return _rag_service


# 便捷函数
def save_document(content: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> List[str]:
    """便捷函数：处理并保存文档"""
    return get_rag_service().save_document(content, metadata, **kwargs)


async def search(query: str, k: int = 4) -> List[Document]:
    """便捷函数：语义搜索"""
    return await get_rag_service().search(query, k)


def search_sync(query: str, k: int = 4) -> List[Document]:
    """便捷函数：同步语义搜索"""
    return get_rag_service().search_sync(query, k)
