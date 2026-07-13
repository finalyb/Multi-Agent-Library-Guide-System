#!/usr/bin/env python3
"""
知识库构建脚本

从 JSON 数据文件构建 RAG 向量索引。
运行方式: python scripts/build_kb.py
"""
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.knowledge.data_loader import kb_loader
from backend.knowledge.rag_pipeline import rag_pipeline
from backend.utils.logger import log, setup_logger


async def main():
    setup_logger()
    log.info("=" * 50)
    log.info("Building knowledge base index...")

    # 加载数据
    kb_loader.load_all()
    docs = kb_loader.get_all_documents()
    log.info(f"Loaded {len(docs)} documents")

    # 按类型统计
    types = {}
    for doc in docs:
        t = doc["metadata"].get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    for t, count in types.items():
        log.info(f"  {t}: {count} documents")

    # 构建RAG索引
    await rag_pipeline.build_index_async()

    from backend.knowledge.vector_store import vector_store
    log.info("Knowledge base index built successfully!")
    log.info(f"Total vectors: {vector_store.count()}")
    log.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
