"""
DGX Spark Hackathon - 图书馆新生AI导览助手
FastAPI 主入口

启动方式:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import uuid
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path

from backend.config import settings
from backend.utils.logger import log, setup_logger
from backend.agents.orchestrator import orchestrator
from backend.agents.memory import memory_store
from backend.knowledge.data_loader import kb_loader
from backend.knowledge.rag_pipeline import rag_pipeline


# ===== 生命周期 =====

async def _preload_embedder():
    """预加载嵌入模型，避免首次请求阻塞"""
    try:
        from backend.models.local_embedder import local_embedder
        await local_embedder.embed(["test"])
        log.info("Embedding model preloaded successfully")
    except Exception as e:
        log.warning(f"Embedding model preload failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的生命周期管理"""
    # 启动
    setup_logger()
    log.info("=" * 50)
    log.info("图书馆新生AI导览助手 - Starting up")
    log.info(f"Model: {settings.STEPFUN_MODEL}")
    log.info(f"Debug: {settings.DEBUG}")

    # 加载知识库
    kb_loader.load_all()
    log.info(f"Knowledge base loaded: {len(kb_loader.get_all_documents())} documents")

    # 预加载嵌入模型（后台）
    asyncio.create_task(_preload_embedder())

    # 构建RAG索引（后台异步，不阻塞启动）
    try:
        asyncio.create_task(rag_pipeline.build_index_async())
        log.info("RAG index build started in background")
    except Exception as e:
        log.warning(f"RAG index build skipped: {e}")

    log.info("Server ready! 访问 http://localhost:8000 体验")

    yield

    # 关闭
    log.info("Server shutting down")


# ===== FastAPI App =====

app = FastAPI(
    title="图书馆新生AI导览助手",
    description="基于 NVIDIA DGX Spark + Stepfun 阶跃星辰 Step 3.7 Flash 的多智能体图书馆导览系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 请求/响应模型 =====

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    intent: str = ""
    search_sources: list[dict] = []
    verify_result: dict | None = None
    path_info: dict | None = None
    target_location: str | None = None
    processing_time_ms: float = 0.0


# ===== API 路由 =====

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "model": settings.STEPFUN_MODEL,
        "active_sessions": memory_store.active_sessions,
        "knowledge_docs": len(kb_loader.get_all_documents()),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    对话接口（非流式）

    完整的Agent流水线：
    意图分类 → 知识检索 → 路径规划(如需要) → 回复生成 → 事实校验

    Request: {"message": "借阅规则是什么？", "session_id": "abc123"}
    """
    if not request.message.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "消息不能为空"},
        )

    try:
        result = await orchestrator.process(
            user_message=request.message.strip(),
            session_id=request.session_id,
        )
        return ChatResponse(**result)
    except Exception as e:
        log.exception(f"Chat error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "处理请求时出错",
                "detail": str(e) if settings.DEBUG else "请稍后重试",
            },
        )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    流式对话接口（SSE）

    用于前端实时展示打字效果，体验更好。
    事件类型:
      - token: 文本增量
      - done: 流结束
      - error: 错误

    Request: {"message": "怎么去期刊阅览室？", "session_id": "abc123"}
    """
    if not request.message.strip():
        return JSONResponse(status_code=400, content={"error": "消息不能为空"})

    async def generate():
        try:
            async for chunk in orchestrator.process_stream(
                user_message=request.message.strip(),
                session_id=request.session_id,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            log.exception(f"Stream error: {e}")
            yield f"data: [ERROR: {str(e)}]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/upload/image")
async def upload_image(
    image: UploadFile = File(...),
    session_id: str = Form(default=""),
):
    """
    图片上传接口 - 多模态识别

    用户拍照上传书架/图书封面 → Step 3.7 Flash 多模态识别 → 返回位置/图书信息

    Request: multipart/form-data {image: file, session_id: "abc123"}
    """
    if not session_id:
        session_id = str(uuid.uuid4())[:8]

    # 读取并编码图片
    contents = await image.read()
    image_base64 = base64.b64encode(contents).decode("utf-8")

    # 大小限制检查（10MB）
    if len(contents) > 10 * 1024 * 1024:
        return JSONResponse(
            status_code=400,
            content={"error": "图片过大，请压缩至10MB以内"},
        )

    try:
        result = await orchestrator.process(
            user_message="[用户上传了一张图片]",
            session_id=session_id,
            user_image_base64=image_base64,
        )
        return result
    except Exception as e:
        log.exception(f"Image upload error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "图片处理失败，请重试", "detail": str(e) if settings.DEBUG else ""},
        )


@app.post("/admin/rebuild-kb")
async def rebuild_knowledge_base():
    """
    重建知识库索引（管理接口）

    当知识库JSON文件更新后调用此接口重新构建向量索引。
    """
    try:
        kb_loader._loaded = False  # 强制重新加载
        kb_loader.load_all()
        await rag_pipeline.build_index_async()
        return {
            "status": "ok",
            "documents": len(kb_loader.get_all_documents()),
            "vectors": rag_pipeline.vector_store.count() if hasattr(rag_pipeline, 'vector_store') else 0,
        }
    except Exception as e:
        log.exception(f"Rebuild KB error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """获取会话信息（调试用）"""
    session = memory_store.get(session_id)
    if not session:
        return {"error": "会话不存在或已过期"}
    return {
        "session_id": session_id,
        "message_count": len(session.conversation_history),
        "current_intent": session.current_intent,
        "current_location": session.current_location,
        "last_active": session.last_active,
    }


# ===== 静态文件（前端） =====

frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    log.info(f"Frontend mounted from: {frontend_dir}")


# ===== 启动入口 =====

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
