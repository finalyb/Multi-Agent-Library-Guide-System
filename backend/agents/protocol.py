"""
Multi-Agent 通信协议

定义Agent间消息的标准格式、角色枚举、意图分类。
这是整个多智能体系统的基础契约——每个Agent都必须遵守。
"""
from dataclasses import dataclass, field
from enum import Enum
import uuid
import time


# ===== Agent 角色 =====

class AgentRole(str, Enum):
    """Agent角色枚举 - 每个Agent有明确的身份"""
    GUIDE = "guide"           # 导览Agent：对话+意图路由
    SEARCH = "search"         # 检索Agent：RAG查询
    PLANNING = "planning"     # 规划Agent：路径生成
    VERIFY = "verify"         # 校验Agent：幻觉检测
    ORCHESTRATOR = "orchestrator"  # 编排器：总调度


# ===== 消息类型 =====

class MessageType(str, Enum):
    # 请求
    INTENT_CLASSIFY = "intent_classify"     # 意图分类
    RAG_QUERY = "rag_query"                 # 知识检索
    PATH_PLAN = "path_plan"                 # 路径规划
    VERIFY = "verify"                       # 事实校验
    IMAGE_UNDERSTAND = "image_understand"   # 多模态识别
    # 响应
    INTENT_RESULT = "intent_result"
    RAG_RESULT = "rag_result"
    PATH_RESULT = "path_result"
    VERIFY_RESULT = "verify_result"
    IMAGE_RESULT = "image_result"
    # 控制
    ERROR = "error"
    HEARTBEAT = "heartbeat"


# ===== 用户意图 =====

class UserIntent(str, Enum):
    """用户意图分类 - Guide Agent的输出"""
    POLICY_QUERY = "policy_query"        # 借阅规则/规章制度类问题
    LOCATION_WHERE = "location_where"    # 位置查询（我在哪/XX在哪）
    NAVIGATE_TO = "navigate_to"          # 导航请求（怎么去XX）
    BOOK_LOOKUP = "book_lookup"          # 图书查找
    OPENING_HOURS = "opening_hours"      # 开馆时间
    FACILITY_QUERY = "facility_query"    # 设施查询（打印/存包/研讨室等）
    GENERAL_CHAT = "general_chat"        # 闲聊/问候
    IMAGE_QUERY = "image_query"          # 图片查询（拍照识别）
    UNKNOWN = "unknown"


# ===== Agent 消息 =====

@dataclass
class AgentMessage:
    """Agent间通信的标准消息格式"""
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str = ""
    sender: AgentRole = AgentRole.ORCHESTRATOR
    receiver: AgentRole = AgentRole.GUIDE
    msg_type: MessageType = MessageType.INTENT_CLASSIFY
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    parent_msg_id: str | None = None  # 用于跟踪消息链

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "session_id": self.session_id,
            "sender": self.sender.value,
            "receiver": self.receiver.value,
            "msg_type": self.msg_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "parent_msg_id": self.parent_msg_id,
        }


# ===== 上下文传递（Agent间共享） =====

@dataclass
class AgentContext:
    """
    Agent执行上下文

    在Orchestrator流转过程中，各Agent通过Context共享中间结果。
    这是"有边界、有记忆"中"记忆"的实现。
    """
    session_id: str
    user_message: str = ""
    user_image_base64: str | None = None
    intent: UserIntent = UserIntent.UNKNOWN
    intent_confidence: float = 0.0
    search_results: list[dict] = field(default_factory=list)
    path_result: dict | None = None
    verify_result: dict | None = None
    current_location: str | None = None
    target_location: str | None = None
    final_response: str = ""

    def to_summary(self) -> str:
        """生成上下文摘要（用于日志和调试）"""
        parts = [
            f"Intent: {self.intent.value} ({self.intent_confidence:.2f})",
            f"Current: {self.current_location or 'unknown'}",
            f"Target: {self.target_location or 'N/A'}",
            f"Search hits: {len(self.search_results)}",
            f"Path: {'✓' if self.path_result else '✗'}",
            f"Verify: {'✓' if self.verify_result else '✗'}",
        ]
        return " | ".join(parts)
