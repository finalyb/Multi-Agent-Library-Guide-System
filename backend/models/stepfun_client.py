"""
Stepfun 阶跃星辰 Step 3.7 Flash 模型客户端

封装三种核心能力：
1. 多轮对话 (chat)
2. 多模态理解 (chat_with_image) - Flash 原生多模态
3. 文本嵌入 (embed) - 用于 RAG 向量检索

基于 OpenAI-compatible API 协议
"""
import base64
import time
from typing import Optional, AsyncGenerator
from openai import AsyncOpenAI
from backend.config import settings
from backend.utils.logger import log


class StepFunClient:
    """
    Step 3.7 Flash API 封装

    Flash 模型核心优势：
    - 原生多模态理解（视觉+文本+视频）
    - 高可靠工具调用（function calling）
    - 长上下文支持（256K tokens，适合携带完整楼层信息）
    - reasoning_effort 推理强度控制（low/medium/high 三档）
    - 低延迟推理（适合导览场景的实时交互）
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.STEPFUN_API_KEY,
            base_url=settings.STEPFUN_BASE_URL,
            timeout=settings.STEPFUN_TIMEOUT,
        )
        self.model = settings.STEPFUN_MODEL
        self._cache: dict = {}  # 简单 LRU 缓存

    # ===== 对话能力 =====

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[list[dict]] = None,
        reasoning_effort: Optional[str] = None,
    ) -> dict:
        """
        多轮对话接口

        Args:
            messages: 对话历史 [{"role": "user/assistant", "content": "..."}]
            system_prompt: 系统提示词
            temperature: 生成温度 (意图分类用0.1, 对话用0.7)
            max_tokens: 最大生成token数
            tools: Function calling 工具定义列表
            reasoning_effort: Stepfun 独有参数，推理强度控制
                - "low": 简单问答、意图分类、查询改写
                - "medium": 一般推理和多步骤任务（默认）
                - "high": 复杂推理、规划、分析

        Returns:
            {
                "content": "回复文本",
                "tool_calls": [...],  # 如果有工具调用
                "usage": {"prompt_tokens": ..., "completion_tokens": ...},
                "latency_ms": ...
            }
        """
        start = time.time()
        full_messages = []

        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})

        full_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            log.error(f"Stepfun chat API error: {e}")
            raise

        latency = (time.time() - start) * 1000
        choice = response.choices[0]
        result = {
            "content": choice.message.content or "",
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            "latency_ms": round(latency, 1),
        }

        # 处理工具调用
        if choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "function": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.message.tool_calls
            ]

        return result

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        reasoning_effort: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式对话接口 - 用于前端 SSE 实时展示

        Yields:
            每次 yield 一段文本增量
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        try:
            stream = await self.client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            log.error(f"Stepfun stream API error: {e}")
            raise

    # ===== 多模态理解 =====

    async def chat_with_image(
        self,
        image_base64: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> dict:
        """
        多模态理解接口 - 拍照识别书架/图书封面

        Step 3.7 Flash 原生支持图文混合输入，无需额外视觉编码器

        Args:
            image_base64: Base64编码的图片
            prompt: 对图片的提问 ("识别这张照片中的书架位置")
            system_prompt: 系统提示词
            temperature: 视觉理解用低温度 (0.1-0.3) 保证准确性

        Returns:
            同 chat() 返回结构
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        # 复用 chat 方法，OpenAI-compatible 格式
        return await self.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
        )

    # ===== 嵌入能力 =====

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        文本嵌入接口 - 用于 RAG 向量检索

        Args:
            texts: 待嵌入的文本列表（批量处理提高效率）

        Returns:
            嵌入向量列表，每个是 float 数组
        """
        try:
            response = await self.client.embeddings.create(
                model=settings.STEPFUN_EMBEDDING_MODEL,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            log.error(f"Stepfun embedding API error: {e}")
            raise

    async def embed_single(self, text: str) -> list[float]:
        """单条文本嵌入"""
        results = await self.embed([text])
        return results[0]

    # ===== 缓存 =====

    def _cache_key(self, messages: list[dict], temperature: float) -> str:
        """生成缓存键"""
        import hashlib
        import json

        raw = json.dumps({"msgs": messages, "tmp": temperature}, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()


# 全局单例
stepfun_client = StepFunClient()
