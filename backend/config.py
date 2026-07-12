"""
DGX Spark Hackathon - 全局配置管理
基于 pydantic-settings，从 .env 文件和环境变量加载配置
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    """应用全局配置"""

    # ===== 项目路径 =====
    PROJECT_ROOT: Path = Field(default=Path(__file__).parent.parent)
    DATA_DIR: Path = Field(default=Path(__file__).parent.parent / "data")
    KNOWLEDGE_DIR: Path = Field(default=Path(__file__).parent / "knowledge" / "data")

    # ===== Stepfun 阶跃星辰 =====
    STEPFUN_API_KEY: str = Field(default="your_stepfun_api_key_here")
    STEPFUN_BASE_URL: str = Field(default="https://api.stepfun.com/v1")
    STEPFUN_MODEL: str = Field(default="step-3.7-flash")
    STEPFUN_EMBEDDING_MODEL: str = Field(default="step-3.7-flash")
    STEPFUN_MAX_TOKENS: int = Field(default=2048)
    STEPFUN_TEMPERATURE: float = Field(default=0.7)
    STEPFUN_TIMEOUT: int = Field(default=30)  # seconds

    # ===== NVIDIA Nemotron (本地推理后备) =====
    NEMOTRON_MODEL_PATH: Optional[str] = Field(default=None)
    NEMOTRON_ENGINE_PATH: Optional[str] = Field(default=None)
    USE_NEMOTRON_FALLBACK: bool = Field(default=True)

    # ===== ChromaDB =====
    CHROMA_PERSIST_DIR: str = Field(default="./data/chroma_db")
    CHROMA_COLLECTION_NAME: str = Field(default="library_knowledge")

    # ===== RAG 配置 =====
    RAG_TOP_K: int = Field(default=5)
    RAG_SIMILARITY_THRESHOLD: float = Field(default=0.6)
    RAG_CHUNK_SIZE: int = Field(default=500)
    RAG_CHUNK_OVERLAP: int = Field(default=100)
    RAG_USE_HYBRID: bool = Field(default=True)  # 混合检索 (向量+BM25)

    # ===== 服务配置 =====
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=True)
    LOG_LEVEL: str = Field(default="INFO")

    # ===== 对话记忆 =====
    SESSION_TTL_SECONDS: int = Field(default=1800)  # 30分钟过期
    MAX_HISTORY_TURNS: int = Field(default=10)

    # ===== MySQL 馆藏数据库（只读） =====
    MYSQL_HOST: str = Field(default="172.16.71.21")
    MYSQL_USER: str = Field(default="myview")
    MYSQL_PASSWORD: str = Field(default="yangbo19861022")
    MYSQL_DATABASE: Optional[str] = Field(default=None)
    MYSQL_CHARSET: str = Field(default="utf8mb4")

    # ===== DGX Spark 云节点 =====
    DGX_SPARK_HOST: Optional[str] = Field(default=None)
    DGX_SPARK_PORT: Optional[int] = Field(default=8000)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# 全局单例
settings = Settings()
