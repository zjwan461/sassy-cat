"""
文档分块，写入知识库，知识库语义查询，列表查询等
"""

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
import paths
import config_loader
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)
from langchain_core.documents import Document
from uuid import uuid4

config_loader.load_config("C:\\Users\\1\\AppData\\Roaming\\sassy-cat\\config.user.json")
model_name = "BAAI/bge-small-zh-v1.5"
# 本地已下载模型就填本地路径："./models/bge-large-zh-v1.5"

import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
model_kwargs = {"device": device, "trust_remote_code": True}
encode_kwargs = {"normalize_embeddings": True}

bge_embeddings = HuggingFaceEmbeddings(
    model_name=model_name, model_kwargs=model_kwargs, encode_kwargs=encode_kwargs
)

cfg = config_loader.current()
remote_embeddings = OpenAIEmbeddings(
    base_url=cfg.get("rag.embeddingModel.baseUrl"),
    api_key=cfg.get("rag.embeddingModel.apiKey"),
    model=cfg.get("rag.embeddingModel.model"),
    check_embedding_ctx_length=False,
)
# 测试接口，和OpenAIEmbeddings完全一致
# q_vec = bge_embeddings.embed_query("什么是RAG")
# doc_vecs = bge_embeddings.embed_documents(["文档1内容","文档2内容"])
# print(len(q_vec))

chroma_dir = paths.data_dir() + "/chroma"
vector_store = Chroma(
    collection_name="sassy-kb",
    # embedding_function=bge_embeddings,
    embedding_function=remote_embeddings,
    persist_directory=chroma_dir,
    # other params...
)


def test_embedding():
    """单独测试 embedding 是否正常工作"""
    print("\n=== 测试 Embedding ===")
    try:
        print("测试 embed_query...")
        q_vec = bge_embeddings.embed_query("什么是RAG")
        print(f"embed_query 成功，向量维度: {len(q_vec)}")

        print("测试 embed_documents...")
        doc_vecs = bge_embeddings.embed_documents(["foo", "thud", "test"])
        print(
            f"embed_documents 成功，生成 {len(doc_vecs)} 个向量，维度: {len(doc_vecs[0])}"
        )
        return True
    except Exception as e:
        print(f"Embedding 测试失败: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


def save_to_chroma():
    import sys

    print("\n=== 保存到 Chroma ===")
    from langchain_core.documents import Document

    document_1 = Document(page_content="foo", metadata={"baz": "bar"})
    document_2 = Document(page_content="thud", metadata={"bar": "baz"})
    document_3 = Document(page_content="i will be deleted :(")

    documents = [document_1, document_2, document_3]
    ids = ["1", "2", "3"]
    print(f"准备写入 {len(documents)} 个文档，ids: {ids}")
    sys.stdout.flush()

    # 步骤1: 测试 embedding
    print("[步骤1] 测试 embed_documents...")
    sys.stdout.flush()
    texts = [doc.page_content for doc in documents]
    embeddings = bge_embeddings.embed_documents(texts)
    print(
        f"[步骤1] embed_documents 成功，生成 {len(embeddings)} 个向量，维度: {len(embeddings[0])}"
    )
    sys.stdout.flush()

    # 步骤2: 检查 embeddings 类型
    print("[步骤2] 检查 embeddings 类型...")
    sys.stdout.flush()
    print(f"[步骤2] embeddings 类型: {type(embeddings)}")
    print(f"[步骤2] embeddings[0] 类型: {type(embeddings[0])}")
    print(f"[步骤2] embeddings[0][0] 类型: {type(embeddings[0][0])}")
    print(f"[步骤2] embeddings[0][0] 值: {embeddings[0][0]}")
    sys.stdout.flush()

    # 步骤2a: 尝试转为 numpy
    print("[步骤2a] 尝试转 numpy...")
    sys.stdout.flush()
    import numpy as np

    emb_np = np.array(embeddings, dtype=np.float32)
    print(f"[步骤2a] numpy shape: {emb_np.shape}, dtype: {emb_np.dtype}")
    sys.stdout.flush()

    # 步骤2b: 直接用 chromadb 原生客户端
    print("[步骤2b] 测试 chromadb 原生客户端...")
    sys.stdout.flush()
    import chromadb

    print(f"[步骤2b] chromadb 版本: {chromadb.__version__}")
    sys.stdout.flush()

    # 创建原生客户端测试
    client = chromadb.PersistentClient(path=chroma_dir + "_test")
    col = client.get_or_create_collection(name="test-col")
    print("[步骤2b] 原生客户端 collection 创建成功")
    sys.stdout.flush()

    # 先测试不带 embeddings 的 upsert
    print("[步骤2c] 测试不带 embeddings 的 upsert...")
    sys.stdout.flush()
    try:
        col2 = client.get_or_create_collection(name="test-col2")
        col2.add(documents=texts, ids=ids)
        print("[步骤2c] 不带 embeddings 的 add 成功")
        sys.stdout.flush()
    except Exception as e:
        print(f"[步骤2c] 失败: {type(e).__name__}: {e}")
        sys.stdout.flush()

    # 测试带 embeddings 的 add
    print("[步骤2d] 测试带 embeddings 的 add...")
    sys.stdout.flush()
    try:
        col3 = client.get_or_create_collection(name="test-col3")
        col3.add(embeddings=embeddings, documents=texts, ids=ids)
        print("[步骤2d] 带 embeddings 的 add 成功")
        sys.stdout.flush()
    except Exception as e:
        print(f"[步骤2d] 失败: {type(e).__name__}: {e}")
        sys.stdout.flush()

    # 步骤3: 测试 add_documents
    print("[步骤3] 测试 add_documents...")
    sys.stdout.flush()
    text_ids = vector_store.add_documents(documents=documents, ids=["4", "5", "6"])
    print(f"[步骤3] add_documents 返回: {text_ids}")
    sys.stdout.flush()

    print("save ok")
    return text_ids


async def rag_save_end_to_end():
    # read document by ocr
    from ocr.ocr_engine import do_ocr

    ocr_result = None
    with open(r"D:/download/SpringBoot框架技术开发文档.md", "br") as file:
        file_bytes = file.read()
        ocr_result = await do_ocr("rag", "1.md", file_bytes)

    if ocr_result is None or not ocr_result.get("page_content"):
        return

    import re

    def is_markdown(text: str) -> bool:
        """
        判断文本是否为 Markdown
        :param text: 输入文本
        :return: True=Markdown  False=普通文本
        """
        if not text or len(text) < 3:
            return False

        # 定义MD特征正则规则
        md_patterns = [
            r"^#{1,6}\s+",  # 标题 # ##
            r"^\d+\.\s+",  # 有序列表 1.
            r"^[\-*]\s+",  # 无序列表 - *
            r"\*\*.+?\*\*",  # 加粗 **text**
            r"\*.+?\*",  # 斜体 *text*
            r"\[.+?\]\(.+?\)",  # 链接 [text](url)
            r"!\[.+?\]\(.+?\)",  # 图片 ![](url)
            r"```[\s\S]*?```",  # 代码块
            r"\|.+\|",  # 表格
            r"^\s*---+\s*$",  # 分割线
        ]

        score = 0
        for p in md_patterns:
            if re.search(p, text, re.MULTILINE):
                score += 1

        # 特征命中 ≥2 判定为 Markdown（容错极高，几乎不误判）
        return score >= 2

    content = ocr_result.get("page_content")
    docs = Document(page_content=content, metadata=ocr_result.get("metadata"))
    if is_markdown(content):
        text_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2")]
        )
        raw_splits = text_splitter.split_text(docs.page_content)
        # 把原文档metadata附加给每个分块
        all_splits = []
        for s in raw_splits:
            s.metadata.update(docs.metadata)
            all_splits.append(s)
    else:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        all_splits = text_splitter.split_documents(docs)

    # 过滤空内容，确保 page_content 为非空字符串
    all_splits = [
        doc for doc in all_splits if doc.page_content and doc.page_content.strip()
    ]

    if not all_splits:
        print("警告：文档分块后无有效内容，跳过写入")
        return

    ids = [str(uuid4()) for _ in range(len(all_splits))]
    vector_store.add_documents(all_splits, ids=ids)


async def search(text: str):
    retrieved_docs = vector_store.similarity_search(query=text, k=4)
    print(retrieved_docs)


async def get_chunks():
    collection = vector_store._collection
    ids = collection.get(where={"kb_id": "default"}, include=[])["ids"]
    print(ids)
    result = collection.get(
        where=None,
        limit=10,
        offset=0,
        include=["documents", "metadatas"],
    )
    print(result)
    return result


if __name__ == "__main__":

    # import sys

    # print(f"Python: {sys.version}")
    # print(f"Chroma 目录: {chroma_dir}")

    # # 先测试 embedding
    # if not test_embedding():
    #     print("Embedding 测试失败，跳过 Chroma 写入")
    #     sys.exit(1)

    # # 再测试 Chroma
    # try:
    #     text_ids = save_to_chroma()
    #     print(f"\n最终结果 text_ids: {text_ids}")
    # except Exception as e:
    #     print(f"\n程序执行失败: {type(e).__name__}: {e}")
    #     import traceback

    #     traceback.print_exc()
    #     sys.exit(1)
    import asyncio

    # asyncio.run(rag_save_end_to_end())
    # asyncio.run(search("spring"))
    asyncio.run(get_chunks())
    print("\n=== 完成 ===")
