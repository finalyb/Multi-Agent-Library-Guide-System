"""
检索Agent (Search Agent)

职责：RAG知识检索，返回相关文档片段和置信度
角色边界：不直接回应用户、不分类意图、不计算路径

这是知识库的唯一入口 —— 所有信息查询都通过Search Agent
"""
from backend.agents.base import BaseAgent
from backend.agents.protocol import AgentRole, AgentContext, UserIntent
from backend.knowledge.rag_pipeline import rag_pipeline
from backend.knowledge.data_loader import kb_loader
from backend.utils.logger import log


# ====== 查询重写 System Prompt ======

QUERY_REWRITE_PROMPT = """将用户的自然语言问题改写为更适合知识库检索的查询语句。

规则：
1. 提取核心关键词
2. 补充可能的同义词和相关词
3. 保持简洁（不超过30个字）
4. 如果是位置查询，补充楼层和区域信息

用户问题：{user_query}
意图类型：{intent}

只输出改写后的查询语句，不要其他内容。"""


class SearchAgent(BaseAgent):
    """
    检索Agent — 知识库检索的唯一入口

    边界：
    - 可以做：RAG查询、文档检索、查询重写
    - 不能做：生成用户回复、意图分类、路径计算、事实核查
    """

    role = AgentRole.SEARCH
    allowed_actions = ["rag_query", "query_rewrite", "keyword_search"]
    forbidden_actions = ["generate_user_response", "intent_classification", "path_calculation"]

    async def execute(self, context: AgentContext) -> AgentContext:
        """执行知识检索"""
        intent = context.intent

        # Step 1: 直接用原始查询（改写会导致关键词丢失）
        search_query = context.user_message

        # Step 2: 根据意图类型确定检索过滤器
        doc_type, category, floor = self._get_search_filters(intent, context.user_message)

        # Step 3: 执行检索
        try:
            results = await rag_pipeline.retrieve_with_rerank(
                query=search_query,
                top_k=5,
                doc_type=doc_type,
                category=category,
                floor=floor,
            )
        except Exception as e:
            log.error(f"[Search] RAG retrieval failed: {e}")
            # 降级：关键词搜索
            results = rag_pipeline._fallback_keyword_search(search_query, top_k=5)

        context.search_results = results

        # 同时提取位置信息（如果是位置查询）
        if intent in [UserIntent.LOCATION_WHERE, UserIntent.NAVIGATE_TO, UserIntent.BOOK_LOOKUP]:
            self._extract_location_info(context, results)

        log.info(
            f"[Search] Found {len(results)} results for: {search_query[:50]}"
        )
        return context

    # ===== 私有方法 =====

    async def _rewrite_query(self, user_query: str, intent: str) -> str:
        """使用 Step 3.7 Flash 重写查询，优化检索效果"""
        try:
            response = await stepfun_client.chat(
                messages=[{"role": "user", "content": QUERY_REWRITE_PROMPT.format(
                    user_query=user_query,
                    intent=intent,
                )}],
                temperature=0.3,
                max_tokens=50,
                reasoning_effort="low",  # 查询重写：简单任务
            )
            rewritten = response["content"].strip()
            log.debug(f"[Search] Query rewritten: '{user_query[:30]}...' → '{rewritten}'")
            return rewritten
        except Exception:
            # 降级：直接用原始查询
            return user_query

    def _get_search_filters(
        self, intent: UserIntent, message: str
    ) -> tuple:
        """
        根据意图和消息内容确定检索过滤条件

        Returns:
            (doc_type, category, floor)
        """
        doc_type = None
        category = None
        floor = None

        if intent == UserIntent.POLICY_QUERY:
            doc_type = "rule"
            if "借" in message or "还" in message or "册" in message:
                category = "借阅规则"
            elif "座" in message or "预约" in message:
                category = "座位预约"
            elif "电子" in message or "数据库" in message or "知网" in message:
                category = "数字资源"
            elif "入馆" in message or "带" in message:
                category = "入馆须知"
            elif "安静" in message or "讨论" in message:
                category = "阅览规则"

        elif intent == UserIntent.LOCATION_WHERE:
            # 先查FAQ中的馆藏分布，再查具体位置
            if "文" in message or "小说" in message:
                category = "馆藏分布"
                floor = "2F"
            elif "计算" in message or "编程" in message or "技术" in message:
                category = "馆藏分布"
                floor = "3F"
            elif "期刊" in message or "报纸" in message:
                category = "馆藏分布"
                floor = "3F"
            elif "古籍" in message:
                floor = "4F"
            elif "研讨" in message:
                floor = "3F"

        elif intent == UserIntent.BOOK_LOOKUP:
            doc_type = "faq"
            category = "馆藏分布"

        elif intent == UserIntent.OPENING_HOURS:
            category = "开馆信息"

        elif intent == UserIntent.FACILITY_QUERY:
            doc_type = "faq"

        return doc_type, category, floor

    def _extract_location_info(self, context: AgentContext, results: list[dict]) -> None:
        """从检索结果中提取位置信息"""
        for doc in results:
            metadata = doc.get("metadata", {})
            if metadata.get("type") == "location":
                floor = metadata.get("floor", "")
                zone_name = metadata.get("zone_name", "")
                if floor and zone_name:
                    context.target_location = f"{floor} {zone_name}"
                    break

        # 如果没有精确匹配，用关键词在楼层数据中搜索
        if not context.target_location:
            message = context.user_message
            zones = kb_loader.search_zone_by_name(message[:20])
            if zones:
                z = zones[0]
                context.target_location = f"{z['floor']} {z['name']}"


# 延迟导入以避免循环引用
from backend.models.stepfun_client import stepfun_client
