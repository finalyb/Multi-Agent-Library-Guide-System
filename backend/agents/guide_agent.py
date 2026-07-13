"""
导览Agent (Guide Agent)

职责：对话交互 + 意图分类 + 最终回复合成
角色边界：不直接查库、不计算路径、不做事实核查

这是用户唯一直接对话的Agent —— 用户看到的每一句话都由Guide Agent发出
"""
import json
from backend.agents.base import BaseAgent
from backend.agents.protocol import AgentRole, AgentContext, UserIntent
from backend.models.stepfun_client import stepfun_client
from backend.utils.logger import log


# ===== 意图分类 System Prompt =====

INTENT_CLASSIFY_PROMPT = """你是图书馆AI导览助手的意图分类器。分析用户消息，判断其意图。

意图类别（7种）：
1. policy_query — 借阅规则、规章制度、罚款、赔偿、续借流程等
2. location_where — 询问某物在哪、某类书在哪、某区域在哪
3. navigate_to — 请求从A到B的导航路径、路线指引
4. book_lookup — 查找具体图书、索书号查询、图书检索
5. opening_hours — 开放时间、节假日安排、考试周安排
6. facility_query — 设施使用（打印/复印/存包/研讨室/WiFi等）
7. general_chat — 问候、闲聊、感谢、再见等非信息查询
8. image_query — 用户上传了图片（拍照识别书架、图书封面等）
9. unknown — 无法判断

请输出JSON格式：
{"intent": "policy_query", "confidence": 0.95, "reasoning": "简短说明"}

只输出JSON，不要其他内容。"""


# ===== 对话生成 System Prompt =====

CONVERSATION_PROMPT = """你是「吉利学院图书馆」的AI导览助手，名字叫"吉小图"。

身份设定：
- 你是吉利学院图书馆专属的智能导览员，不是通用AI助手
- 永远不要说自己是什么"通义千问"、"Qwen"或其他AI模型
- 如果有人问你是谁，回答"我是吉小图，吉利学院图书馆的AI导览助手~"
- 有人问你能做什么，围绕图书馆服务回答（找书、导航、借阅规则、座位预约等）
- 语气友善、耐心，用大学生喜欢的风格交流

回答原则：基于检索结果回答，简洁实用（150字内），不编造。如果检索结果没有相关信息，诚实说明并建议联系总服务台。

检索上下文：
{search_context}

对话历史：
{conversation_history}

请用吉小图的身份回答用户问题："""


class GuideAgent(BaseAgent):
    """
    导览Agent — 用户交互的唯一入口

    边界：
    - 可以做：意图分类、对话生成、回复合成
    - 不能做：直接查库（交给Search Agent）、路径计算（交给Planning Agent）、事实核查（交给Verify Agent）
    """

    role = AgentRole.GUIDE
    allowed_actions = ["intent_classify", "generate_response"]
    forbidden_actions = ["direct_db_query", "path_calculation", "fact_verification"]

    async def execute(self, context: AgentContext) -> AgentContext:
        """执行导览Agent任务：意图分类 → 路由"""
        log.info(f"[Guide] Processing: {context.user_message[:50]}...")

        # Step 1: 意图分类
        intent, confidence = await self._classify_intent(
            context.user_message,
            has_image=bool(context.user_image_base64),
        )
        context.intent = intent
        context.intent_confidence = confidence
        log.info(f"[Guide] Intent: {intent.value} (confidence: {confidence:.2f})")

        return context

    async def generate_response(self, context: AgentContext) -> str:
        """
        生成最终用户回复

        根据不同类型的结果合成回复：
        - 如果有检索结果 → 基于RAG结果生成
        - 如果有路径 → 组织路径描述
        - 如果只是一般对话 → 直接回复
        """
        intent = context.intent

        if intent == UserIntent.GENERAL_CHAT:
            return await self._generate_chat_response(context.user_message)

        # 构建检索上下文
        search_context = self._build_search_context(context)

        # 构建对话历史
        conv_history = ""
        if self.session:
            conv_history = self.session.get_conversation_context()

        prompt = CONVERSATION_PROMPT.format(
            search_context=search_context,
            conversation_history=conv_history,
        )

        messages = [{"role": "user", "content": context.user_message}]

        # 如果有路径结果，追加路径信息
        if context.path_result:
            path_text = self._format_path(context.path_result)
            messages.append({
                "role": "user",
                "content": f"[系统消息] 已生成导航路径如下，请用自然语言告知用户：\n{path_text}",
            })

        try:
            response = await stepfun_client.chat(
                messages=messages,
                system_prompt=prompt,
                temperature=0.7,
                reasoning_effort="medium",  # 一般推理：基于检索结果生成回复
            )
            return response["content"]
        except Exception as e:
            log.error(f"[Guide] Response generation failed: {e}")
            return "抱歉，我暂时无法回答这个问题，请稍后再试或到1F总服务台咨询（电话：028-XXXX-XXXX）。"

    async def generate_response_stream(self, context: AgentContext):
        """流式生成回复（用于SSE）"""
        intent = context.intent

        if intent == UserIntent.GENERAL_CHAT:
            async for chunk in stepfun_client.chat_stream(
                messages=[{"role": "user", "content": context.user_message}],
                temperature=0.7,
            ):
                yield chunk
            return

        search_context = self._build_search_context(context)
        conv_history = self.session.get_conversation_context() if self.session else ""

        prompt = CONVERSATION_PROMPT.format(
            search_context=search_context,
            conversation_history=conv_history,
        )

        messages = [{"role": "user", "content": context.user_message}]

        if context.path_result:
            path_text = self._format_path(context.path_result)
            messages.append({
                "role": "user",
                "content": f"[系统消息] 已生成导航路径：\n{path_text}",
            })

        try:
            async for chunk in stepfun_client.chat_stream(
                messages=messages,
                system_prompt=prompt,
                temperature=0.7,
            ):
                yield chunk
        except Exception as e:
            log.error(f"[Guide] Stream generation failed: {e}")
            yield "抱歉，我暂时无法回答这个问题。"

    # ===== 私有方法 =====

    async def _classify_intent(
        self, message: str, has_image: bool = False
    ) -> tuple[UserIntent, float]:
        """使用 Step 3.7 Flash 进行意图分类"""
        if has_image:
            return UserIntent.IMAGE_QUERY, 1.0

        try:
            response = await stepfun_client.chat(
                messages=[{"role": "user", "content": message}],
                system_prompt=INTENT_CLASSIFY_PROMPT,
                temperature=0.1,  # 低温度保证分类稳定
                max_tokens=100,
                reasoning_effort="low",  # 简单分类任务
            )

            # 解析JSON
            content = response["content"].strip()
            # 处理可能的markdown代码块包裹
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            result = json.loads(content)

            intent_str = result.get("intent", "unknown")
            confidence = float(result.get("confidence", 0.5))

            # 映射到枚举
            intent_map = {
                "policy_query": UserIntent.POLICY_QUERY,
                "location_where": UserIntent.LOCATION_WHERE,
                "navigate_to": UserIntent.NAVIGATE_TO,
                "book_lookup": UserIntent.BOOK_LOOKUP,
                "opening_hours": UserIntent.OPENING_HOURS,
                "facility_query": UserIntent.FACILITY_QUERY,
                "general_chat": UserIntent.GENERAL_CHAT,
                "image_query": UserIntent.IMAGE_QUERY,
            }
            intent = intent_map.get(intent_str, UserIntent.UNKNOWN)
            return intent, confidence

        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"[Guide] Intent classification parse error: {e}")
            # 降级：关键词匹配
            return self._fallback_intent_classify(message), 0.5
        except Exception as e:
            log.error(f"[Guide] Intent classification error: {e}")
            return UserIntent.UNKNOWN, 0.0

    def _fallback_intent_classify(self, message: str) -> UserIntent:
        """降级意图分类：关键词匹配"""
        keywords = {
            UserIntent.POLICY_QUERY: ["借", "还", "规则", "罚", "赔", "续借", "期限", "超期"],
            UserIntent.LOCATION_WHERE: ["在哪", "哪里", "什么位置", "几楼", "哪个区"],
            UserIntent.NAVIGATE_TO: ["怎么去", "怎么走", "路线", "导航", "带路"],
            UserIntent.BOOK_LOOKUP: ["书", "查找", "检索", "索书号", "作者"],
            UserIntent.OPENING_HOURS: ["开门", "关门", "时间", "几点", "周末", "假期"],
            UserIntent.FACILITY_QUERY: ["打印", "复印", "WiFi", "无线", "存包", "研讨", "充电"],
        }
        for intent, kws in keywords.items():
            if any(kw in message for kw in kws):
                return intent
        return UserIntent.GENERAL_CHAT

    def _build_search_context(self, context: AgentContext) -> str:
        """构建检索上下文文本（精简版，减少本地LLM处理时间）"""
        if not context.search_results:
            return "暂无相关检索结果。"

        lines = []
        for i, doc in enumerate(context.search_results[:3]):  # 只取Top-3
            lines.append(f"[{i+1}] {doc['content'][:200]}")   # 截断到200字
        return "\n".join(lines)

    def _format_path(self, path_result: dict) -> str:
        """格式化路径信息"""
        parts = []
        if path_result.get("from_location"):
            parts.append(f"起点：{path_result['from_location']}")
        if path_result.get("to_location"):
            parts.append(f"终点：{path_result['to_location']}")
        if path_result.get("directions"):
            parts.append("路线：")
            for step in path_result["directions"]:
                parts.append(f"  → {step}")
        return "\n".join(parts) if parts else "路径信息不可用"

    async def _generate_chat_response(self, message: str) -> str:
        """处理闲聊类消息 — 走 Stepfun 确保身份一致"""
        chat_prompt = """你是「吉利学院图书馆」的AI导览助手，名字叫"吉小图"。

身份设定：
- 你是吉利学院图书馆专属的智能导览员
- 性格友善、耐心、热情，用大学生喜欢的语气交流
- 对图书馆每一层、每一个书架都了如指掌
- 永远不要说自己是什么"通义千问"或"Qwen"或其他AI模型
- 如果有人问你是谁，回答"我是吉小图，吉利学院图书馆的AI导览助手~"
- 如果有人问你能做什么，围绕图书馆服务来回答（找书、导航、借阅规则、开放时间等）

回复要求：2-3句话，简洁自然，引导用户提出图书馆相关问题。"""

        try:
            response = await stepfun_client.chat(
                messages=[{"role": "user", "content": message}],
                system_prompt=chat_prompt,
                temperature=0.8,
                max_tokens=200,
                use_local=False,  # 走 Stepfun, 确保身份正确
            )
            return response["content"]
        except Exception:
            return "你好！我是图书馆导览助手吉小图，有什么可以帮你的吗？😊"
