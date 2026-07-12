"""
共享会话记忆层

实现"有角色、有边界、有记忆"中的"记忆"机制：
- 每个会话维护独立的上下文
- 短期记忆：当前对话的上下文（最近N轮对话 + 当前中间状态）
- TTL自动过期（30分钟未活跃的会话自动清理）
"""
import time
from dataclasses import dataclass, field
from typing import Optional
from backend.config import settings
from backend.utils.logger import log


@dataclass
class SessionContext:
    """单个会话的完整上下文"""
    session_id: str
    conversation_history: list[dict] = field(default_factory=list)  # [{"role":"user/assistant","content":"..."}]
    current_intent: Optional[str] = None
    retrieved_docs: list[dict] = field(default_factory=list)        # 当前轮RAG结果
    current_location: Optional[str] = None                          # 用户最后确认的位置
    pending_confirmations: list[str] = field(default_factory=list)  # 待确认项
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str) -> None:
        """添加一条对话记录"""
        self.conversation_history.append({"role": role, "content": content})
        # 保持最近N轮
        max_msgs = settings.MAX_HISTORY_TURNS * 2
        if len(self.conversation_history) > max_msgs:
            self.conversation_history = self.conversation_history[-max_msgs:]
        self.last_active = time.time()

    def get_conversation_context(self) -> str:
        """获取对话上下文的文本表示"""
        if not self.conversation_history:
            return "（新对话）"
        lines = []
        for msg in self.conversation_history[-4:]:  # 最近2轮
            role = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role}: {msg['content'][:100]}")
        return "\n".join(lines)

    def clear_turn_state(self) -> None:
        """清除当前轮的状态，保留对话历史"""
        self.current_intent = None
        self.retrieved_docs = []
        self.pending_confirmations = []

    def is_expired(self, ttl_seconds: int = 1800) -> bool:
        """检查会话是否过期"""
        return time.time() - self.last_active > ttl_seconds


class MemoryStore:
    """
    In-Memory 会话存储

    选择内存存储的原因：
    1. Hackathon demo阶段无需Redis依赖
    2. 单用户demo场景，内存足够
    3. 升级到Redis仅需替换此类
    """

    def __init__(self, ttl_seconds: int = 1800):
        self._store: dict[str, SessionContext] = {}
        self._ttl = ttl_seconds

    def get_or_create(self, session_id: str) -> SessionContext:
        """获取或创建会话"""
        self.cleanup_expired()

        if session_id not in self._store:
            self._store[session_id] = SessionContext(session_id=session_id)
            log.debug(f"Created new session: {session_id}")
        else:
            self._store[session_id].last_active = time.time()

        return self._store[session_id]

    def get(self, session_id: str) -> Optional[SessionContext]:
        """获取会话（不自动创建）"""
        ctx = self._store.get(session_id)
        if ctx and not ctx.is_expired(self._ttl):
            return ctx
        elif ctx:
            del self._store[session_id]
        return None

    def update(self, session_id: str, **kwargs) -> None:
        """更新会话属性"""
        ctx = self.get_or_create(session_id)
        for key, value in kwargs.items():
            if hasattr(ctx, key):
                setattr(ctx, key, value)
        ctx.last_active = time.time()

    def clear(self, session_id: str) -> None:
        """清除会话"""
        if session_id in self._store:
            del self._store[session_id]
            log.debug(f"Cleared session: {session_id}")

    def cleanup_expired(self) -> int:
        """清理过期会话"""
        expired = [
            sid
            for sid, ctx in self._store.items()
            if ctx.is_expired(self._ttl)
        ]
        for sid in expired:
            del self._store[sid]
        if expired:
            log.debug(f"Cleaned up {len(expired)} expired sessions")
        return len(expired)

    @property
    def active_sessions(self) -> int:
        """活跃会话数"""
        self.cleanup_expired()
        return len(self._store)


# 全局单例
memory_store = MemoryStore(ttl_seconds=settings.SESSION_TTL_SECONDS)
