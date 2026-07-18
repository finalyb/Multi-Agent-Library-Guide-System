# 📚 吉小图 — 图书馆新生AI导览助手

> **基于 NVIDIA DGX Spark × Stepfun 阶跃星辰 的多智能体图书馆导览系统**
> 
> 🏆 2026 DGX Spark Hackathon 参赛作品 | 吉利学院图书馆团队

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Stepfun](https://img.shields.io/badge/Model-Step%203.7%20Flash-orange.svg)](https://stepfun.com)
[![NVIDIA](https://img.shields.io/badge/NVIDIA-DGX%20Spark-76B900.svg)](https://nvidia.com)
[![GPU](https://img.shields.io/badge/GPU-Qwen3.6%20MoE-red.svg)](https://github.com/ggerganov/llama.cpp)

---

## 🎯 核心亮点

**新生拍照书架 → AI识别位置 → 给出步行导航 → 告诉这个区域有什么书**

三个Demo场景，一个手机搞定：
- 📷 **拍照导航** — 拍书架照片，秒知"你在XX区XX排"
- 💬 **智能问答** — 借阅规则、开放时间、馆藏分布，即问即答
- 🗺️ **路径规划** — "怎么去期刊阅览室？"→ 分步导航指引

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────┐
│           前端 Mobile-First Web               │
│     📷 拍照上传 │ 💬 文本对话 │ 🗺️ 路径展示     │
└──────────────────┬───────────────────────────┘
                   │ HTTP/SSE
┌──────────────────▼───────────────────────────┐
│          FastAPI 后端 (DGX Spark)             │
│  ┌─────────────────────────────────────────┐ │
│  │      Multi-Agent 编排 (Orchestrator)     │ │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │ │
│  │  │Guide │ │Search│ │Plan  │ │Verify│  │ │
│  │  │ 对话 │ │ RAG  │ │ A*  │ │ 校验 │  │ │
│  │  └──────┘ └──────┘ └──────┘ └──────┘  │ │
│  │       共享记忆层 (SessionContext)        │ │
│  └─────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────┐ │
│  │     混合 RAG 检索引擎                    │ │
│  │  ChromaDB + BM25 关键词 + RRF 融合      │ │
│  └─────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────┐ │
│  │            模型层                        │ │
│  │  🧠 Qwen3.6 MoE (本地GPU推理)           │ │
│  │  🔌 Step 3.7 Flash (多模态理解)         │ │
│  │  ⚡ TensorRT / RAPIDS (推理加速)        │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

## 🧠 Multi-Agent 设计

四个Agent，**有角色、有边界、有记忆**：

| Agent | 职责 | 能做什么 | 不能做什么 |
|-------|------|:--------:|:---------:|
| **Guide Agent** | 对话交互 + 意图路由 | 意图分类、回复合成、多模态识别 | ❌ 直接查库、计算路径 |
| **Search Agent** | RAG知识检索 | 向量检索、BM25关键词、查询重写 | ❌ 回应用户、生成路径 |
| **Planning Agent** | 路径规划 | A*算法、楼层图导航、方向生成 | ❌ 对话交互、事实核查 |
| **Verify Agent** | 幻觉检测 | 事实与知识库比对、不一致标记 | ❌ 生成内容、修改回复 |

> 💡 **设计理念**：Agent 间通过 `AgentContext` 共享状态（记忆），通过 `allowed_actions`/`forbidden_actions` 强制执行边界约束。借鉴上一届获奖作品 "Starfire-AgentTeam" 的核心理念——从"单兵作战"到"组织化协作"。
数据基于测试数据
---

## 🔧 技术栈

| 类别 | 组件 | 用途说明 |
|------|------|---------|
| **AI模型** | **Stepfun 阶跃星辰 Step 3.7 Flash** | 多模态理解（拍照识别书架/图书封面）、意图分类、回复生成 |
| **AI模型** | **Qwen3.6-35B-A3B MoE (4bit)** | DGX Spark 本地GPU推理，35B总参/3B激活 |
| **NVIDIA SDK** | **TensorRT-LLM** | 本地模型推理加速，INT8量化 |
| **NVIDIA SDK** | **RAPIDS cuDF** | RAG检索结果GPU加速处理 |
| **向量数据库** | **ChromaDB** | 知识库向量存储与语义检索 |
| **后端** | **FastAPI + Uvicorn** | 异步API服务，SSE流式响应 |
| **前端** | **原生 HTML/CSS/JS** | 移动端优先，零构建步骤 |
| **推理引擎** | **llama.cpp (CUDA)** | Qwen3.6 MoE GPU推理服务 |

---

## 📖 知识库

基于真实图书馆场景构建：

- **50条FAQ** — 借阅规则、开馆时间、座位预约、馆藏分布、设施使用
- **25条规章制度** — 入馆、借阅、阅览、数字资源、违规处理
- **4层楼面数据** — 30+区域节点、80+条导航边
- **A*路径图** — 支持跨楼层导航（电梯/楼梯）
- **MySQL 馆藏同步** — 对接图书馆真实数据库，支持增量更新

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- NVIDIA DGX Spark
- Stepfun API Key

### 安装

```bash
git clone https://github.com/finalyb/Multi-Agent-Library-Guide-System.git
cd Multi-Agent-Library-Guide-System
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填写 STEPFUN_API_KEY 等

# 构建知识库
python scripts/build_kb.py

# 启动
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### DGX Spark 本地模型部署

```bash
# 编译 llama.cpp (CUDA)
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=native
cmake --build build --config Release -j$(nproc)

# 下载 Qwen3.6-MoE GGUF 模型 (ModelScope 国内源)
# 模型: Qwen3.6-35B-A3B-MXFP4_MOE.gguf (~21GB)

# 启动 GPU 推理服务
./llama-server -m <model.gguf> -ngl 99 -fa on \
  -c 32768 --parallel 2 --cont-batching \
  -ctk q4_0 -ctv q4_0 --mlock \
  --host 0.0.0.0 --port 8080

# 启动 Web 服务
uvicorn backend.main:app --host 0.0.0.0 --port 8888
```

---

## 📱 功能演示

| 场景 | 用户输入 | 吉小图回复 |
|------|---------|-----------|
| 身份识别 | "你是谁" | 我是吉小图，吉利学院图书馆的AI导览助手~ |
| 拍照导航 | 📸 拍书架照片 | 您在2F文学区推荐书架，索书号I247.5... |
| 文本问答 | "借阅规则是什么" | 本科生10册/30天，研究生15册，可续借... |
| 路径规划 | "怎么去期刊阅览室" | 从2F直走到电梯→上3F→出电梯右转到底→到达！ |

---

## 📂 项目结构

```
├── README.md                  # 本文件
├── docs/                      # 参赛文档
│   ├── 项目说明文档.md          # 项目详细说明（≥600字）
│   ├── 部署说明.md             # DGX Spark 部署步骤
│   ├── 技术栈说明.md           # 技术组件使用详解
│   └── library-ai-guide.mp4   # 作品演示视频
├── backend/
│   ├── main.py                # FastAPI 入口
│   ├── config.py              # 配置管理
│   ├── agents/                # Multi-Agent 系统
│   │   ├── orchestrator.py    # 编排器（核心调度）
│   │   ├── guide_agent.py     # 导览Agent
│   │   ├── search_agent.py    # 检索Agent
│   │   ├── planning_agent.py  # 规划Agent（含A*算法）
│   │   ├── verify_agent.py    # 校验Agent
│   │   ├── protocol.py        # 通信协议
│   │   └── memory.py          # 共享记忆层
│   ├── knowledge/             # 知识库
│   │   ├── rag_pipeline.py    # 混合RAG管道
│   │   ├── vector_store.py    # ChromaDB封装
│   │   ├── data_loader.py     # 数据加载器
│   │   └── data/              # JSON知识库
│   ├── models/                # 模型层
│   │   ├── stepfun_client.py  # 混合路由客户端
│   │   └── local_embedder.py  # 本地嵌入引擎
│   └── services/
│       └── mysql_client.py    # MySQL馆藏同步
├── frontend/                  # 移动端前端
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js             # 主逻辑
│       ├── chat.js            # 对话模块
│       ├── camera.js          # 拍照模块
│       └── api.js             # API通信
└── scripts/
    ├── build_kb.py            # 知识库构建
    └── sync_mysql_to_kb.py    # MySQL数据同步
```

---

## 👥 团队

- **团队名称**：吉利学院图书馆团队
- **单位**：吉利学院图书馆
- **团队成员**：杨博，杨帅，高智洪

---

*本项目为 2026 DGX Spark Hackathon 参赛作品，基于 NVIDIA DGX Spark × Stepfun 阶跃星辰平台构建。*
