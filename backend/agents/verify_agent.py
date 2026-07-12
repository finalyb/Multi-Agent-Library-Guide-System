"""
校验Agent (Verify Agent)

职责：幻觉检测 —— 验证 Agent 输出与知识库原文的一致性
角色边界：不生成新内容、不参与对话、不做检索

这是"负责任AI"的体现 —— 防止给用户错误信息
"""
from backend.agents.base import BaseAgent
from backend.agents.protocol import AgentRole, AgentContext
from backend.models.stepfun_client import stepfun_client
from backend.utils.logger import log


# ===== 事实校验 System Prompt =====

VERIFY_PROMPT = """你是图书馆AI导览系统的事实校验员。请判断AI助手的回答是否与知识库原文一致。

## 校验规则
1. 逐条检查回答中的事实陈述（数字、规则、时间、位置等）
2. 与知识库原文比对，判断是否准确
3. 回答中的补充说明（非事实性内容）不需要校验

## 输出格式
请输出JSON：
{
    "is_accurate": true/false,
    "issues": [
        {
            "claim": "回答中的具体陈述",
            "expected": "知识库中的正确表述",
            "severity": "critical/major/minor"
        }
    ],
    "confidence": 0.95,
    "summary": "一句话总结校验结果"
}

只输出JSON，不要其他内容。"""


class VerifyAgent(BaseAgent):
    """
    校验Agent — 幻觉检测的最后一道防线

    边界：
    - 可以做：事实与知识库比对、不一致标记
    - 不能做：生成新内容、修改回答、与用户交互
    """

    role = AgentRole.VERIFY
    allowed_actions = ["fact_check", "consistency_verify"]
    forbidden_actions = ["generate_content", "modify_response", "user_interaction"]

    async def execute(self, context: AgentContext) -> AgentContext:
        """
        执行事实校验

        比较 final_response 与 search_results 的一致性
        """
        if not context.final_response or not context.search_results:
            # 无回复或无检索结果时跳过校验
            context.verify_result = {
                "is_accurate": True,
                "issues": [],
                "confidence": 1.0,
                "summary": "跳过校验（无回复或检索结果）",
                "skipped": True,
            }
            return context

        # 构建校验输入
        knowledge_text = self._build_knowledge_context(context.search_results)

        verify_input = f"""请校验以下AI回答与知识库原文的一致性。

## AI回答
{context.final_response[:1000]}

## 知识库原文
{knowledge_text[:2000]}"""

        try:
            response = await stepfun_client.chat(
                messages=[{"role": "user", "content": verify_input}],
                system_prompt=VERIFY_PROMPT,
                temperature=0.1,
                max_tokens=300,
                reasoning_effort="medium",  # 事实校验需要仔细比对
            )

            # 解析结果
            import json
            content = response["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            result = json.loads(content)
            context.verify_result = {
                "is_accurate": result.get("is_accurate", True),
                "issues": result.get("issues", []),
                "confidence": result.get("confidence", 1.0),
                "summary": result.get("summary", ""),
                "skipped": False,
            }

            if not result.get("is_accurate", True):
                issues = result.get("issues", [])
                log.warning(
                    f"[Verify] Found {len(issues)} issues: "
                    + ", ".join(i.get("claim", "")[:50] for i in issues)
                )
            else:
                log.info("[Verify] Response verified - accurate")

        except Exception as e:
            log.error(f"[Verify] Verification failed: {e}")
            context.verify_result = {
                "is_accurate": True,
                "issues": [],
                "confidence": 0.5,
                "summary": f"校验异常: {str(e)[:50]}",
                "skipped": True,
            }

        return context

    async def quick_verify(self, response: str, search_results: list[dict]) -> bool:
        """
        快速校验：检查回答是否包含检索结果中的关键信息

        Args:
            response: AI生成的回答
            search_results: 检索到的知识库文档

        Returns:
            True if likely accurate, False if potential hallucination
        """
        if not search_results:
            return True  # 无参考源，无法校验

        # 简单规则：检查回答中是否有数字和检索结果不一致
        import re

        for doc in search_results[:3]:
            content = doc.get("content", "")
            # 提取检索结果中的数字
            numbers_in_doc = set(re.findall(r"\d+", content))
            numbers_in_response = set(re.findall(r"\d+", response))

            # 如果回答中有检索结果里没有的数字，标记为可疑
            suspicious = numbers_in_response - numbers_in_doc
            if suspicious and len(suspicious) > 2:
                log.debug(f"[Verify] Suspicious numbers detected: {suspicious}")
                return False

        return True

    def _build_knowledge_context(self, search_results: list[dict]) -> str:
        """构建知识库原文上下文"""
        lines = []
        for i, doc in enumerate(search_results[:5]):
            lines.append(f"--- 文档 {i+1} ---")
            lines.append(doc.get("content", ""))
        return "\n".join(lines)
