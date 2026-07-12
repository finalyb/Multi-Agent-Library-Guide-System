"""
ChromaDB 向量存储

用于 RAG 系统的文档向量化存储和语义检索。
支持元数据过滤（按类型、楼层、类别等）。
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import Optional
from pathlib import Path
from backend.config import settings
from backend.utils.logger import log


class VectorStore:
    """
    ChromaDB 封装

    选择 ChromaDB 而非 FAISS 的原因：
    1. Python原生、零配置，适合10天快速开发
    2. 支持元数据过滤（按楼层、类别过滤）
    3. 内建持久化，不需要手动 save/load
    4. 知识库 ~200条，ChromaDB 性能完全够用
    """

    def __init__(self, persist_dir: Optional[str] = None):
        persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection_name = settings.CHROMA_COLLECTION_NAME
        self._collection = None

    @property
    def collection(self):
        """延迟获取或创建collection"""
        if self._collection is None:
            try:
                self._collection = self.client.get_collection(self.collection_name)
                log.info(f"Loaded existing collection: {self.collection_name}")
            except Exception:
                self._collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                log.info(f"Created new collection: {self.collection_name}")
        return self._collection

    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: Optional[list[dict]] = None,
    ) -> None:
        """
        批量添加文档到向量库

        Args:
            ids: 文档唯一标识
            documents: 文档文本内容
            embeddings: 对应的嵌入向量
            metadatas: 元数据（用于过滤）
        """
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        log.info(f"Added {len(ids)} documents to vector store")

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: Optional[dict] = None,
    ) -> dict:
        """
        语义检索

        Args:
            query_embedding: 查询向量
            top_k: 返回结果数
            where: 元数据过滤条件 (ChromaDB where语法)

        Returns:
            {"ids": [...], "documents": [...], "metadatas": [...], "distances": [...]}
        """
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )
        return {
            "ids": results["ids"][0],
            "documents": results["documents"][0],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
            "distances": results["distances"][0],
        }

    def search_by_text(
        self,
        query_embedding: list[float],
        doc_type: Optional[str] = None,
        category: Optional[str] = None,
        floor: Optional[str] = None,
        top_k: int = 5,
    ) -> dict:
        """
        带元数据过滤的语义检索

        Args:
            query_embedding: 查询向量
            doc_type: 文档类型过滤 (faq/rule/location)
            category: FAQ/规章类别过滤
            floor: 楼层过滤 (1F/2F/3F/4F)
            top_k: 返回结果数
        """
        where = {}
        if doc_type:
            where["type"] = doc_type
        if category:
            where["category"] = category
        if floor:
            where["floor"] = floor

        return self.search(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where if where else None,
        )

    def count(self) -> int:
        """返回文档总数"""
        return self.collection.count()

    def clear(self) -> None:
        """清空向量库（用于重建索引）"""
        self.client.delete_collection(self.collection_name)
        self._collection = None
        log.info(f"Cleared collection: {self.collection_name}")

    def rebuild(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: Optional[list[dict]] = None,
    ) -> None:
        """重建索引（先清空再添加）"""
        self.clear()
        self.add_documents(ids, documents, embeddings, metadatas)
        log.info(f"Rebuilt vector store with {len(ids)} documents")


# 全局单例
vector_store = VectorStore()
