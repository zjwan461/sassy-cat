# -*- coding: utf-8 -*-
"""轻量关键词检索：BM25 + RRF，不引入额外依赖。

为什么需要它
------------
纯向量检索（bge/OpenAI embedding）对语义相近的表述很强，但对
「编号、专有名词、代码标识符、精确短语」经常漏召回——例如问
`ERR-4021 怎么解决`，向量可能召回一堆讲"错误处理"的段落，却漏掉
真正出现 `ERR-4021` 的那一块。BM25 正好补这个短板。

设计取舍
--------
- 不装 jieba / rank_bm25：中文用「单字 + 相邻二元组」切分，英文/数字/下划线
  按词切分，对知识库里常见的中英混排足够稳，也避免多一个重依赖。
- 两路结果用 RRF（Reciprocal Rank Fusion）融合，只比较名次不比较原始分数：
  向量距离与 BM25 分数的量纲完全不可比，RRF 是工业界常用的免调参方案。
"""

from __future__ import annotations

import math
import re
from collections import Counter

# 英文/数字/下划线标识符（代码、型号、编号）
_ASCII_RE = re.compile(r"[a-z0-9_]+")
# 汉字（逐字收集后再拼二元组）
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """把一段文本切成检索词：英文词 + 中文单字 + 中文二元组。"""
    text = (text or "").lower()
    tokens = _ASCII_RE.findall(text)
    cjk = _CJK_RE.findall(text)
    if cjk:
        tokens.extend(cjk)
        tokens.extend(a + b for a, b in zip(cjk, cjk[1:]))
    return tokens


class BM25Index:
    """内存 BM25 索引：语料是一批 (id, text)，查询返回 [(id, score)]。"""

    def __init__(self, docs: list[tuple[str, str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.ids: list[str] = []
        self.term_freqs: list[Counter] = []
        self.lengths: list[int] = []
        doc_freq: Counter = Counter()

        for doc_id, text in docs:
            tokens = tokenize(text)
            tf = Counter(tokens)
            self.ids.append(doc_id)
            self.term_freqs.append(tf)
            self.lengths.append(len(tokens))
            doc_freq.update(tf.keys())

        self.n = len(self.ids)
        self.avg_len = (sum(self.lengths) / self.n) if self.n else 0.0
        # 带平滑的 IDF，避免高频词权重为负
        self.idf = {
            term: math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        terms = set(tokenize(query))
        if not terms or not self.n:
            return []

        scores: list[tuple[str, float]] = []
        for i, tf in enumerate(self.term_freqs):
            length = self.lengths[i] or 1
            norm = self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
            score = 0.0
            for term in terms:
                freq = tf.get(term)
                if not freq:
                    continue
                score += self.idf.get(term, 0.0) * freq * (self.k1 + 1) / (freq + norm)
            if score > 0:
                scores.append((self.ids[i], score))

        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:limit]


def rrf_fuse(
    ranked_id_lists: list[list[str]],
    weights: list[float] | None = None,
    rrf_k: int = 60,
) -> dict[str, float]:
    """Reciprocal Rank Fusion：score(d) = Σ weight_i / (rrf_k + rank_i(d))。

    只依赖名次，天然兼容「向量距离」和「BM25 分数」这种不同量纲。
    """
    weights = weights or [1.0] * len(ranked_id_lists)
    scores: dict[str, float] = {}
    for ranked, weight in zip(ranked_id_lists, weights):
        for rank, doc_id in enumerate(ranked, 1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (rrf_k + rank)
    return scores
