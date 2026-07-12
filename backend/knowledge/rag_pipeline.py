"""
混合RAG检索引擎

核心检索流程：
1. 用户查询 → Step 3.7 Flash 生成查询向量
2. ChromaDB 语义检索（向量相似度）
3. (可选) BM25 关键词检索（稀疏召回）
4. RRF 融合排序
5. Step 3.7 Flash 对 Top-N 重排序
6. 返回最相关的 Top-K 文档
"""
import re
import math
from collections import Counter
from typing import Optional
from backend.config import settings
from backend.models.stepfun_client import stepfun_client
from backend.knowledge.vector_store import vector_store
from backend.knowledge.data_loader import kb_loader
from backend.utils.logger import log


class RAGPipeline:
    """
    混合RAG管道

    支持两种检索模式：
    1. 纯向量检索（默认，快速，适合大多数场景）
    2. 混合检索（向量+BM25，准确度更高，适合精确匹配场景）
    """

    def __init__(self):
        self.top_k = settings.RAG_TOP_K
        self.similarity_threshold = settings.RAG_SIMILARITY_THRESHOLD
        self.use_hybrid = settings.RAG_USE_HYBRID
        self._documents: list[dict] = []  # 缓存所有文档用于BM25
        self._bm25_index: Optional[BM25Index] = None

    def build_index(self) -> None:
        """构建RAG索引（启动时调用一次）"""
        log.info("Building RAG index...")

        # 加载所有文档
        self._documents = kb_loader.get_all_documents()
        log.info(f"Loaded {len(self._documents)} documents from knowledge base")

        # 生成嵌入并添加到向量库
        ids = []
        texts = []
        metadatas = []

        for doc in self._documents:
            ids.append(doc["id"])
            texts.append(doc["content"])
            metadatas.append(doc["metadata"])

        # 批量生成嵌入（每批20条）
        batch_size = 20
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                embeddings = stepfun_client.embed(batch)  # 注意：这里是同步调用包装
                # 实际运行时需要用 asyncio.run() 或改为异步
                all_embeddings.extend(embeddings)
                log.info(f"Embedded batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}")
            except Exception as e:
                log.error(f"Embedding failed for batch starting at {i}: {e}")
                # 降级：使用零向量占位
                dim = 1536
                all_embeddings.extend([[0.0] * dim for _ in batch])

        # 写入向量库
        vector_store.rebuild(ids, texts, all_embeddings, metadatas)

        # 构建BM25索引（可选）
        if self.use_hybrid:
            self._bm25_index = BM25Index(texts)

        log.info(f"RAG index built: {vector_store.count()} vectors")

    async def build_index_async(self) -> None:
        """异步构建RAG索引"""
        log.info("Building RAG index (async)...")

        self._documents = kb_loader.get_all_documents()
        log.info(f"Loaded {len(self._documents)} documents from knowledge base")

        ids = []
        texts = []
        metadatas = []

        for doc in self._documents:
            ids.append(doc["id"])
            texts.append(doc["content"])
            metadatas.append(doc["metadata"])

        # 异步批量生成嵌入
        batch_size = 20
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                embeddings = await stepfun_client.embed(batch)
                all_embeddings.extend(embeddings)
                log.info(f"Embedded batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}")
            except Exception as e:
                log.error(f"Embedding failed for batch starting at {i}: {e}")
                dim = 1536
                all_embeddings.extend([[0.0] * dim for _ in batch])

        vector_store.rebuild(ids, texts, all_embeddings, metadatas)

        if self.use_hybrid:
            self._bm25_index = BM25Index(texts)

        log.info(f"RAG index built: {vector_store.count()} vectors")

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        doc_type: Optional[str] = None,
        category: Optional[str] = None,
        floor: Optional[str] = None,
    ) -> list[dict]:
        """
        检索相关文档

        Args:
            query: 用户查询
            top_k: 返回结果数
            doc_type: 文档类型过滤
            category: 类别过滤
            floor: 楼层过滤

        Returns:
            [{"id": ..., "content": ..., "metadata": ..., "score": ...}, ...]
        """
        # Step 1: 生成查询向量
        try:
            query_embedding = await stepfun_client.embed_single(query)
        except Exception as e:
            log.error(f"Query embedding failed: {e}")
            return self._fallback_keyword_search(query, top_k)

        # Step 2: 向量检索
        chroma_results = vector_store.search_by_text(
            query_embedding=query_embedding,
            doc_type=doc_type,
            category=category,
            floor=floor,
            top_k=top_k * 2,  # 多召回一些用于重排序
        )

        vector_results = []
        for i, doc_id in enumerate(chroma_results["ids"]):
            distance = chroma_results["distances"][i]
            similarity = 1 - distance  # cosine distance → similarity
            if similarity >= self.similarity_threshold:
                vector_results.append({
                    "id": doc_id,
                    "content": chroma_results["documents"][i],
                    "metadata": chroma_results["metadatas"][i] if chroma_results["metadatas"] else {},
                    "score": similarity,
                    "source": "vector",
                })

        # Step 3: BM25检索（可选，混合模式）
        if self.use_hybrid and self._bm25_index:
            bm25_results = self._bm25_index.search(query, top_k * 2)
            # RRF融合
            merged = self._rrf_fusion(vector_results, bm25_results, k=60)
        else:
            merged = vector_results

        # Step 4: 截取top_k
        merged = sorted(merged, key=lambda x: x["score"], reverse=True)[:top_k]

        return merged

    async def retrieve_with_rerank(
        self,
        query: str,
        top_k: int = 3,
        **kwargs,
    ) -> list[dict]:
        """
        检索 + Step 3.7 Flash 重排序

        先用向量检索召回top_k*2，再用模型对(query, doc)对打分，
        返回top_k最相关的结果。适合对准确性要求高的场景。
        """
        # 初检索
        candidates = await self.retrieve(query, top_k=top_k * 2, **kwargs)

        if len(candidates) <= top_k:
            return candidates

        # Step 3.7 Flash 重排序
        try:
            reranked = await self._llm_rerank(query, candidates, top_k)
            return reranked
        except Exception as e:
            log.warning(f"LLM rerank failed, using vector scores: {e}")
            return candidates[:top_k]

    async def _llm_rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int,
    ) -> list[dict]:
        """使用 Step 3.7 Flash 对候选文档重排序"""
        # 构建重排序prompt
        candidate_texts = []
        for i, doc in enumerate(candidates):
            candidate_texts.append(f"[{i}] {doc['content'][:200]}")

        prompt = f"""请根据用户查询的相关性，对以下文档片段进行排序。
用户查询：{query}

文档片段：
{chr(10).join(candidate_texts)}

请按相关性从高到低返回前{top_k}个文档编号（格式：用逗号分隔的数字，如 "3,0,5"）。只返回数字。"""

        response = await stepfun_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=50,
            reasoning_effort="low",  # 简单排序任务
        )

        # 解析排序结果
        try:
            ranks = [int(x.strip()) for x in response["content"].split(",")]
            reranked = []
            for r in ranks:
                if 0 <= r < len(candidates):
                    reranked.append(candidates[r])
            # 保底：合并未被排到的
            for i, doc in enumerate(candidates):
                if i not in ranks:
                    reranked.append(doc)
            return reranked[:top_k]
        except (ValueError, IndexError):
            return candidates[:top_k]

    def _rrf_fusion(
        self,
        vector_results: list[dict],
        bm25_results: list[dict],
        k: int = 60,
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion - 融合向量检索和BM25结果
        """
        scores = {}
        docs = {}

        for rank, result in enumerate(vector_results):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
            docs[doc_id] = result

        for rank, result in enumerate(bm25_results):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
            docs[doc_id] = result

        merged = []
        for doc_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            doc = docs[doc_id].copy()
            doc["score"] = score / 2  # normalize
            merged.append(doc)

        return merged

    def _fallback_keyword_search(self, query: str, top_k: int) -> list[dict]:
        """
        降级方案：纯关键词匹配（当向量检索不可用时）
        """
        log.warning("Using fallback keyword search")
        results = []
        query_lower = query.lower()

        for doc in self._documents:
            if query_lower in doc["content"].lower():
                # 简单TF-IDF-like评分
                count = doc["content"].lower().count(query_lower)
                score = min(count / max(len(doc["content"].split()), 1) * 10, 1.0)
                results.append({
                    "id": doc["id"],
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "score": score,
                    "source": "keyword_fallback",
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


class BM25Index:
    """
    轻量级 BM25 关键词检索

    不依赖 Elasticsearch，纯 Python 实现。
    适合 ~200 条文档的小规模检索。
    """

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = documents
        self.N = len(documents)
        self.avgdl = sum(len(d.split()) for d in documents) / max(self.N, 1)
        self._tokenized: list[list[str]] = [self._tokenize(d) for d in documents]
        self._df: Counter = Counter()  # document frequency
        self._idf: dict[str, float] = {}
        self._build_index()

    def _tokenize(self, text: str) -> list[str]:
        """中文+英文混合分词（简易版，生产环境建议用jieba）"""
        # 提取中文2-gram + 英文单词
        tokens = []
        # 英文单词
        tokens.extend(re.findall(r"[a-zA-Z]+", text.lower()))
        # 中文2-gram
        chinese_chars = re.findall(r"[一-鿿]", text)
        for i in range(len(chinese_chars)):
            tokens.append(chinese_chars[i])
            if i < len(chinese_chars) - 1:
                tokens.append(chinese_chars[i] + chinese_chars[i + 1])
        return tokens

    def _build_index(self):
        """构建BM25索引"""
        for tokens in self._tokenized:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self._df[token] += 1

        for token, df in self._df.items():
            self._idf[token] = math.log((self.N - df + 0.5) / (df + 0.5) + 1)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """BM25检索"""
        query_tokens = self._tokenize(query)
        scores = []

        for i, doc_tokens in enumerate(self._tokenized):
            score = 0
            doc_len = len(doc_tokens)
            tf = Counter(doc_tokens)

            for token in query_tokens:
                if token in self._idf:
                    idf = self._idf[token]
                    t = tf.get(token, 0)
                    numerator = t * (self.k1 + 1)
                    denominator = t + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                    score += idf * numerator / max(denominator, 0.1)

            if score > 0:
                scores.append({
                    "id": f"bm25_{i}",
                    "content": self.documents[i],
                    "metadata": {},
                    "score": score / max(score + 1, 1),  # 归一化到 [0, 1)
                    "source": "bm25",
                })

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]


# 全局单例
rag_pipeline = RAGPipeline()
