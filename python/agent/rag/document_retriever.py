"""
文档分块，写入知识库，知识库语义查询，列表查询等
"""

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
import paths

model_name = "BAAI/bge-large-zh-v1.5"
# 本地已下载模型就填本地路径："./models/bge-large-zh-v1.5"

import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
model_kwargs = {"device": device, "trust_remote_code": True}
encode_kwargs = {"normalize_embeddings": True}

bge_embeddings = HuggingFaceEmbeddings(
    model_name=model_name, model_kwargs=model_kwargs, encode_kwargs=encode_kwargs
)

# 测试接口，和OpenAIEmbeddings完全一致
# q_vec = bge_embeddings.embed_query("什么是RAG")
# doc_vecs = bge_embeddings.embed_documents(["文档1内容","文档2内容"])
# print(len(q_vec))

chroma_dir = paths.data_dir() + "/chroma"
vector_store = Chroma(
    collection_name="sassy-kb",
    embedding_function=bge_embeddings,
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
        print(f"embed_documents 成功，生成 {len(doc_vecs)} 个向量，维度: {len(doc_vecs[0])}")
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
    print(f"[步骤1] embed_documents 成功，生成 {len(embeddings)} 个向量，维度: {len(embeddings[0])}")
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


if __name__ == "__main__":
    import sys
    print(f"Python: {sys.version}")
    print(f"Chroma 目录: {chroma_dir}")
    
    # 先测试 embedding
    if not test_embedding():
        print("Embedding 测试失败，跳过 Chroma 写入")
        sys.exit(1)
    
    # 再测试 Chroma
    try:
        text_ids = save_to_chroma()
        print(f"\n最终结果 text_ids: {text_ids}")
    except Exception as e:
        print(f"\n程序执行失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n=== 完成 ===")
