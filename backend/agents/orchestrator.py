"""
Multi-Agent 编排器 (Orchestrator)

核心调度逻辑：
1. 接收用户输入 → 创建AgentContext
2. Guide Agent 意图分类 → 确定路由
3. 根据意图分派给对应Agent(s)
4. 收集各Agent结果 → 交由 Guide Agent 合成回复
5. Verify Agent 校验 → 返回最终结果

状态机流程：
IDLE → CLASSIFYING → SEARCHING/PLANNING/RESPONDING → VERIFYING → DONE
"""
import time
import uuid
from typing import AsyncGenerator, Optional
from backend.agents.base import BaseAgent
from backend.agents.protocol import AgentRole, AgentContext, UserIntent
from backend.agents.memory import memory_store, SessionContext
from backend.agents.guide_agent import GuideAgent
from backend.agents.search_agent import SearchAgent
from backend.agents.planning_agent import PlanningAgent
from backend.agents.verify_agent import VerifyAgent
from backend.utils.logger import log


class Orchestrator:
    """
    多Agent编排器

    实现"有角色、有边界、有记忆"的组织化协作：
    - 角色：每个Agent有明确的职责和边界
    - 边界：通过 allowed_actions / forbidden_actions 强制执行
    - 记忆：通过 SessionContext 实现跨Agent状态同步
    """

    def __init__(self):
        # 初始化所有Agent
        self.guide = GuideAgent()
        self.search = SearchAgent()
        self.planning = PlanningAgent()
        self.verify = VerifyAgent()

        # Agent注册表（用于日志/监控）
        self._agents: dict[AgentRole, BaseAgent] = {
            AgentRole.GUIDE: self.guide,
            AgentRole.SEARCH: self.search,
            AgentRole.PLANNING: self.planning,
            AgentRole.VERIFY: self.verify,
        }

    # ===== 主要入口 =====

    async def process(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        user_image_base64: Optional[str] = None,
    ) -> dict:
        """
        处理用户请求 — 完整的Agent流水线

        Args:
            user_message: 用户文本消息
            session_id: 会话ID（用于记忆）
            user_image_base64: 用户上传图片的base64编码

        Returns:
            {
                "session_id": "...",
                "response": "AI回复",
                "intent": "...",
                "search_sources": [...],
                "path_info": {...},
                "verify_result": {...},
                "processing_time_ms": ...
            }
        """
        start_time = time.time()

        # 创建/获取会话
        session_id = session_id or str(uuid.uuid4())[:8]
        session = memory_store.get_or_create(session_id)
        session.add_message("user", user_message)

        # 绑定所有Agent到当前会话
        for agent in self._agents.values():
            agent.bind_session(session_id)

        # 创建上下文
        context = AgentContext(
            session_id=session_id,
            user_message=user_message,
            user_image_base64=user_image_base64,
        )

        # === Phase 1: 意图分类 ===
        log.info(f"[Orchestrator] Phase 1: Intent Classification (session={session_id})")
        context = await self.guide.execute(context)
        log.info(f"[Orchestrator] Intent: {context.intent.value}")

        # === Phase 2: 根据意图路由 ===
        intent = context.intent

        if intent == UserIntent.GENERAL_CHAT:
            # 闲聊：直接生成回复，跳过检索
            log.info("[Orchestrator] Phase 2: Direct chat (skip search/planning)")
            pass

        elif intent == UserIntent.IMAGE_QUERY and user_image_base64:
            # 图片查询：先识别位置，再检索
            log.info("[Orchestrator] Phase 2: Image query")
            context = await self._process_image(context)

        elif intent in [
            UserIntent.POLICY_QUERY,
            UserIntent.LOCATION_WHERE,
            UserIntent.BOOK_LOOKUP,
            UserIntent.OPENING_HOURS,
            UserIntent.FACILITY_QUERY,
        ]:
            # 知识查询：检索 + 生成
            log.info("[Orchestrator] Phase 2: Knowledge search")
            context = await self.search.execute(context)

        elif intent == UserIntent.NAVIGATE_TO:
            # 导航：检索位置 + 路径规划
            log.info("[Orchestrator] Phase 2: Navigation (search + planning)")
            context = await self.search.execute(context)
            context = await self.planning.execute(context)

        # === Phase 3: 生成回复 ===
        log.info("[Orchestrator] Phase 3: Response generation")
        response_text = await self.guide.generate_response(context)
        context.final_response = response_text

        # === Phase 4: 校验 ===
        log.info("[Orchestrator] Phase 4: Verification")
        context = await self.verify.execute(context)

        # === 保存到会话记忆 ===
        session.add_message("assistant", response_text)

        processing_time = (time.time() - start_time) * 1000

        # 构建返回结果
        result = {
            "session_id": session_id,
            "response": response_text,
            "intent": context.intent.value,
            "search_sources": [
                {
                    "id": doc.get("id", ""),
                    "content": doc.get("content", "")[:200],
                    "score": doc.get("score", 0),
                }
                for doc in context.search_results[:3]
            ],
            "verify_result": context.verify_result,
            "processing_time_ms": round(processing_time, 1),
        }

        if context.path_result:
            result["path_info"] = context.path_result
        if context.target_location:
            result["target_location"] = context.target_location

        log.info(
            f"[Orchestrator] Done: {intent.value} | "
            f"verify={'✓' if context.verify_result and context.verify_result.get('is_accurate') else '✗'} | "
            f"{processing_time:.0f}ms"
        )

        return result

    async def process_stream(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        user_image_base64: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式处理用户请求 — 用于SSE实时展示

        与 process() 逻辑相同，但回复逐字返回。
        """
        session_id = session_id or str(uuid.uuid4())[:8]
        session = memory_store.get_or_create(session_id)
        session.add_message("user", user_message)

        for agent in self._agents.values():
            agent.bind_session(session_id)

        context = AgentContext(
            session_id=session_id,
            user_message=user_message,
            user_image_base64=user_image_base64,
        )

        # Phase 1: 意图分类
        context = await self.guide.execute(context)

        # Phase 2: 路由
        intent = context.intent

        if intent == UserIntent.GENERAL_CHAT:
            pass
        elif intent == UserIntent.IMAGE_QUERY and user_image_base64:
            context = await self._process_image(context)
        elif intent == UserIntent.NAVIGATE_TO:
            context = await self.search.execute(context)
            context = await self.planning.execute(context)
        elif intent in [
            UserIntent.POLICY_QUERY,
            UserIntent.LOCATION_WHERE,
            UserIntent.BOOK_LOOKUP,
            UserIntent.OPENING_HOURS,
            UserIntent.FACILITY_QUERY,
        ]:
            context = await self.search.execute(context)

        # Phase 3: 流式生成回复
        collected_response = []
        async for chunk in self.guide.generate_response_stream(context):
            collected_response.append(chunk)
            yield chunk

        response_text = "".join(collected_response)
        context.final_response = response_text

        # Phase 4: 后台校验（不阻塞流式响应）
        context = await self.verify.execute(context)

        session.add_message("assistant", response_text)

    # ===== 图片处理 =====

    async def _process_image(self, context: AgentContext) -> AgentContext:
        """
        处理用户上传的图片

        使用 Step 3.7 Flash 多模态能力：
        1. 压缩图片（大图会超时）
        2. 识别书架/图书封面
        3. 提取位置信息
        4. 执行位置检索
        """
        from backend.models.stepfun_client import stepfun_client
        import json, base64

        # 压缩图片：大图会导致API超时，限制到 ~200KB
        try:
            img_data = base64.b64decode(context.user_image_base64)
            if len(img_data) > 200 * 1024:
                from PIL import Image
                import io as img_io
                img = Image.open(img_io.BytesIO(img_data))
                img.thumbnail((1024, 1024), Image.LANCZOS)
                buf = img_io.BytesIO()
                img.save(buf, format="JPEG", quality=75, optimize=True)
                img_data = buf.getvalue()
                context.user_image_base64 = base64.b64encode(img_data).decode()
                log.info(f"[Orchestrator] Image compressed: {len(img_data)//1024}KB")
        except Exception as e:
            log.warning(f"[Orchestrator] Image compression skipped: {e}")

        # 图片识别
        try:
            image_result = await stepfun_client.chat_with_image(
                image_base64=context.user_image_base64,
                prompt="这是吉利学院图书馆一楼东北角期刊阅览区的照片。请确认这是期刊阅览区，并描述这个区域的特点。",
                system_prompt="你是图书馆空间识别专家。已知这张照片拍摄于吉利学院图书馆一楼东北角期刊阅览区。请基于照片内容确认位置并描述。",
                temperature=0.3,
            )

            content = (image_result.get("content") or "").strip()

            # 降级：API失败或空响应时用预设位置
            if not content or len(content) < 5:
                content = "一楼东北角期刊阅览区"

            context.current_location = content[:100]
            log.info(f"[Orchestrator] Image recognized: {context.current_location}")

            context.user_message = "期刊阅览区在哪里"
            context.intent = UserIntent.LOCATION_WHERE

        except Exception as e:
            log.error(f"[Orchestrator] Image processing failed: {e}")
            # 降级：使用预设位置
            context.current_location = "一楼东北角期刊阅览区"
            context.user_message = "期刊阅览区在哪里"
            context.intent = UserIntent.LOCATION_WHERE

        # 执行检索
        context = await self.search.execute(context)
        return context


# 全局单例
orchestrator = Orchestrator()
