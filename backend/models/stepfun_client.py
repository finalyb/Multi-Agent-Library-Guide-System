"""
统一模型客户端 — 混合路由架构

策略:
  - 意图分类/查询重写/校验 → Stepfun API (快速, <1s)
  - 最终回复生成 → 本地 llama-server Qwen3.6 GPU
  - 多模态(图片识别) → Stepfun API (唯一支持)
  - 嵌入 → 本地 sentence-transformers

这充分利用了 DGX Spark 本地算力, 同时 Stepfun 处理轻量快速调用
"""
import base64
import time
from typing import Optional, AsyncGenerator
from openai import AsyncOpenAI
from backend.config import settings
from backend.utils.logger import log


class StepFunClient:
    """
    混合路由模型客户端

    - 轻量调用 (intent/rewrite/verify): Stepfun API, temperature=0.1, 快速
    - 重量调用 (response generation): 本地 Qwen3.6 GPU, temperature=0.7
    - 多模态 (image): Stepfun API
    """

    def __init__(self):
        # Stepfun 客户端 (轻量调用 + 多模态)
        self.stepfun = AsyncOpenAI(
            api_key=settings.STEPFUN_API_KEY,
            base_url=settings.STEPFUN_BASE_URL,
            timeout=settings.STEPFUN_TIMEOUT,
        )

        # 本地 LlamaCpp 客户端 (回复生成主力)
        self.local = AsyncOpenAI(
            api_key="not-needed",
            base_url="http://127.0.0.1:8080/v1",
            timeout=120,
        )

    # ===== 混合路由: chat =====

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        tools: Optional[list[dict]] = None,
        reasoning_effort: Optional[str] = None,
        use_local: Optional[bool] = None,
    ) -> dict:
        """
        对话接口 - 自动路由
        """
        if use_local is None:
            use_local = False  # 默认 Stepfun(快速), 本地GPU需显式 use_local=True

        client = self.local if use_local else self.stepfun
        model = "qwen" if use_local else settings.STEPFUN_MODEL
        backend = "local_gpu" if use_local else "stepfun"

        start = time.time()
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # 本地模型: 限制生成长度以加速
        actual_max = min(max_tokens, 256) if use_local else max_tokens

        kwargs = {
            "model": model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": actual_max,
        }

        # Stepfun 特有参数
        if not use_local and reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        # 本地模型: 传递额外参数禁用 thinking
        if use_local:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        # 重试逻辑 (Stepfun API 偶发限流)
        import asyncio as _asyncio
        response = None
        for attempt in range(3):
            try:
                response = await client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                if attempt < 2:
                    wait = (attempt + 1) * 2
                    log.warning(f"{backend} retry {attempt+1}/3 in {wait}s: {e}")
                    await _asyncio.sleep(wait)
                else:
                    log.error(f"{backend} all 3 attempts failed: {e}")

        if response is None:
            if use_local:
                return await self.chat(messages, system_prompt, temperature, max_tokens, tools, reasoning_effort, use_local=False)
            return {
                "content": "抱歉，AI 服务暂时不可用，请稍后重试。",
                "usage": {}, "latency_ms": 0, "backend": "fallback",
            }

        latency = (time.time() - start) * 1000
        choice = response.choices[0]
        content = choice.message.content or ""

        # 处理本地模型空响应
        if use_local and not content and temperature >= 0.5:
            log.warning("Local LLM returned empty, retrying with Stepfun")
            return await self.chat(messages, system_prompt, temperature, max_tokens, tools, reasoning_effort, use_local=False)

        result = {
            "content": content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            "latency_ms": round(latency, 1),
            "backend": backend,
        }

        return result

    # ===== 流式 =====

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        reasoning_effort: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式 - 本地 GPU"""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        try:
            stream = await self.local.chat.completions.create(
                model="qwen",
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            log.error(f"Local stream error: {e}")
            yield "抱歉，服务暂时不可用。"

    # ===== 多模态 (Stepfun) =====

    async def chat_with_image(
        self,
        image_base64: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> dict:
        """多模态 — 始终走 Stepfun (本地模型无视觉能力)"""
        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": prompt},
            ],
        }]
        full = []
        if system_prompt:
            full.append({"role": "system", "content": system_prompt})
        full.extend(messages)

        start = time.time()
        try:
            resp = await self.stepfun.chat.completions.create(
                model=settings.STEPFUN_MODEL,
                messages=full,
                temperature=temperature,
                max_tokens=1024,
            )
            return {
                "content": resp.choices[0].message.content or "",
                "usage": {
                    "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                    "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                },
                "latency_ms": round((time.time() - start) * 1000, 1),
                "backend": "stepfun_multimodal",
            }
        except Exception as e:
            log.error(f"Stepfun multimodal error: {e}")
            return {
                "content": "抱歉，图片识别失败，请重试。",
                "usage": {}, "latency_ms": 0, "backend": "error",
            }

    # ===== 嵌入 (本地) =====

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from backend.models.local_embedder import local_embedder
        return await local_embedder.embed(texts)

    async def embed_single(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]


stepfun_client = StepFunClient()
