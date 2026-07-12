"""
Agent 基类

定义所有Agent的通用接口：
- 角色标识 (role)
- 边界约束 (allowed_actions / forbidden_actions)
- 记忆访问 (memory)
- 执行入口 (execute)

评审关键点："有角色、有边界、有记忆"的组织化协作
"""
from abc import ABC, abstractmethod
from typing import Optional
from backend.agents.protocol import AgentRole, AgentContext
from backend.agents.memory import memory_store, SessionContext
from backend.utils.logger import log


class BaseAgent(ABC):
    """
    Agent 基类

    每个Agent都有：
    1. 明确的角色 (role) — 我是谁
    2. 明确的边界 (allowed/forbidden) — 我能做什么、不能做什么
    3. 记忆访问 (session) — 我能记住什么
    """

    # 子类必须定义
    role: AgentRole

    # 边界定义：子类可覆盖
    allowed_actions: list[str] = []
    forbidden_actions: list[str] = []

    def __init__(self):
        self._session: Optional[SessionContext] = None

    @property
    def session(self) -> Optional[SessionContext]:
        return self._session

    def bind_session(self, session_id: str) -> None:
        """绑定会话 — 获取当前会话的记忆"""
        self._session = memory_store.get_or_create(session_id)

    def remember(self, key: str, value) -> None:
        """写入共享记忆"""
        if self._session:
            setattr(self._session, key, value)

    def recall(self, key: str, default=None):
        """读取共享记忆"""
        if self._session:
            return getattr(self._session, key, default)
        return default

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentContext:
        """
        执行Agent任务

        Args:
            context: 当前Agent上下文（包含上游Agent的输出）

        Returns:
            更新后的Agent上下文（传递给下游Agent）
        """
        ...

    def check_boundary(self, action: str) -> bool:
        """
        边界检查：判断当前Agent是否有权限执行某操作

        Returns:
            True if allowed, False if forbidden
        """
        if action in self.forbidden_actions:
            log.warning(f"[{self.role.value}] Boundary violation: tried to {action}")
            return False
        if self.allowed_actions and action not in self.allowed_actions:
            log.warning(f"[{self.role.value}] Action not in allowed list: {action}")
            return False
        return True

    def __repr__(self) -> str:
        return f"<{self.role.value} Agent>"
