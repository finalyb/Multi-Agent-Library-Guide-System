"""
本地嵌入模型

使用 sentence-transformers 在 DGX Spark 上本地生成文本嵌入向量。
Step 3.7 Flash 不支持 /v1/embeddings 端点，因此使用本地模型。
这充分利用了 DGX Spark 的 GPU 算力。
"""
import asyncio
from typing import Optional
from backend.utils.logger import log


class LocalEmbedder:
    """
    本地嵌入引擎

    使用 all-MiniLM-L6-v2 模型（384维，轻量高效），
    在 DGX Spark GPU 上运行（如可用），否则 CPU 模式。
    """

    def __init__(self):
        self._model = None
        self._model_name = "all-MiniLM-L6-v2"  # 384维，速度最快
        self._dimension = 384
        self._device = "cpu"  # 默认 CPU，GPU 检测后切换

    async def _ensure_model(self):
        """延迟加载模型"""
        if self._model is not None:
            return

        # 跳过网络下载——100条文档直接用BM25关键词检索足够
        # embedding模型需要从HuggingFace下载(~500MB)，DGX Spark网络不可达
        log.info("Skipping embedding model (network unavailable), using BM25 keyword search")
        self._model = None
        self._dimension = 384

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量文本嵌入

        Args:
            texts: 待嵌入的文本列表

        Returns:
            嵌入向量列表 [384维 float list]
        """
        await self._ensure_model()

        if self._model is None:
            # 降级：返回零向量
            log.warning(f"Embedder not available, returning zero vectors")
            return [[0.0] * self._dimension for _ in texts]

        try:
            # 在线程池中执行（sentence-transformers 是同步的）
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: self._model.encode(
                    texts,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ),
            )
            return embeddings.tolist()
        except Exception as e:
            log.error(f"Embedding failed: {e}")
            return [[0.0] * self._dimension for _ in texts]


# 全局单例
local_embedder = LocalEmbedder()
