# 📚 图书馆新生AI导览助手 — "吉小图"

> **基于 NVIDIA DGX Spark × Stepfun 阶跃星辰 Step 3.7 Flash 的多智能体图书馆导览系统**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Stepfun](https://img.shields.io/badge/Stepfun-Step%203.7%20Flash-orange.svg)](https://stepfun.com)
[![NVIDIA](https://img.shields.io/badge/NVIDIA-DGX%20Spark-76B900.svg)](https://nvidia.com)

---

## 🎯 一句话说清楚

**新生拍照书架 → AI秒回"你在XX区XX排" → 给出步行导航 → 告诉你这个区域有什么书。**

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────┐
│              前端 (Mobile-First Web)           │
│        📷 拍照上传 │ 💬 文本对话 │ 🗺️ 路径展示   │
└────────────────────┬─────────────────────────┘
                     │ HTTP/SSE
┌────────────────────▼─────────────────────────┐
│             FastAPI 后端 (DGX Spark)           │
│  ┌───────────────────────────────────────┐   │
│  │     Multi-Agent 编排层 (Orchestrator)   │   │
│  │  ┌────────┐┌────────┐┌────────┐┌────┐│   │
│  │  │ Guide  ││ Search ││Planning││Verify││   │
│  │  │ Agent  ││ Agent  ││ Agent  ││Agent ││   │
│  │  │对话+意图││RAG检索 ││路径规划││幻觉检测││   │
│  │  └────────┘└────────┘└────────┘└────┘│   │
│  │         共享记忆层 (SessionContext)     │   │
│  └───────────────────────────────────────┘   │
│  ┌───────────────────────────────────────┐   │
│  │     RAG 混合检索引擎                    │   │
│  │  ChromaDB 向量库 + BM25 + RRF 融合     │   │
│  └───────────────────────────────────────┘   │
│  ┌───────────────────────────────────────┐   │
│  │     模型层                              │   │
│  │  Step 3.7 Flash │ Nemotron │ TensorRT  │   │
│  └───────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

## 🧠 Multi-Agent 设计（评审核心）

四个 Agent，**有角色、有边界、有记忆**：

| Agent | 职责 | 能做 | 不能做 |
|-------|------|:----:|:-----:|
| **Guide Agent** | 对话交互 + 意图路由 | 意图分类、回复合成 | ❌ 直接查库、路径计算 |
| **Search Agent** | RAG知识检索 | 向量检索、查询重写 | ❌ 回应用户、生成路径 |
| **Planning Agent** | 路径规划 | A*路径计算、导航生成 | ❌ 对话、事实核查 |
| **Verify Agent** | 幻觉检测 | 事实核查、不一致标记 | ❌ 生成内容、修改回复 |

> 💡 **设计理念**：Agent之间通过 `AgentContext` 共享中间结果（记忆），通过 `allowed_actions`/`forbidden_actions` 强制执行边界约束。这是上一届获奖项目"Starfire-AgentTeam"的核心理念——从"单兵作战"到"组织化协作"。

## 🔧 技术栈

| 类别 | 组件 | 用途说明 |
|------|------|---------|
| **AI模型** | **Stepfun 阶跃星辰 Step 3.7 Flash** | 多模态理解（拍照识别书架/图书封面）、对话生成、意图分类、工具调用、文本嵌入 |
| **AI模型** | **NVIDIA Nemotron-4** | 本地推理后备模型、Verify Agent 交叉校验 |
| **NVIDIA SDK** | **TensorRT-LLM** | Step 3.7 Flash 推理加速，INT8量化 |
| **NVIDIA SDK** | **RAPIDS cuDF** | RAG检索结果的GPU加速处理 |
| **向量数据库** | **ChromaDB** | 知识库向量存储与语义检索 |
| **后端** | **FastAPI + Uvicorn** | 异步API服务，SSE流式响应 |
| **前端** | **原生 HTML/CSS/JS** | 移动端优先的轻量UI，零构建步骤 |

## 📖 知识库

基于吉利学院图书馆真实数据构建，包含：

- **50条FAQ** — 覆盖借阅规则、开馆时间、座位预约、馆藏分布、设施使用等
- **25条规章制度** — 入馆须知、借阅规则、阅览规则、数字资源使用规范
- **4层楼面数据** — 含30+区域节点和80+条导航边
- **A*路径图** — 支持跨楼层导航（电梯/楼梯）

## 🚀 快速开始

### DGX Spark 云节点信息

| 项目 | 值 |
|------|-----|
| 机器编号 | **spark-78** |
| 公网 IP | **106.13.186.155** |
| SSH 端口 | **6078** |
| Web 公网端口 | **8078**（内网 8888） |

### 1. 连接 DGX Spark

```bash
# SSH 连接
ssh -p 6078 Developer@106.13.186.155
# 密码: rS6HJ4

# 或使用 Windows 快速脚本
powershell -File scripts/dgx_connect.ps1
```

### 2. 环境准备

```bash
# 克隆项目（在远程机器上）
git clone <your-repo-url> ~/library-ai-guide
cd ~/library-ai-guide

# 安装依赖
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 配置 .env（已预填 API Key 和 MySQL 信息）
```

### 3. 同步数据 & 构建索引

```bash
python scripts/sync_mysql_to_kb.py   # 从MySQL同步真实馆藏
python scripts/build_kb.py           # 构建RAG向量索引
```

### 4. 启动服务

```bash
# ⚠️ 务必使用 8888 端口（映射到公网 8078）
uvicorn backend.main:app --host 0.0.0.0 --port 8888 --workers 2

# 后台运行
nohup uvicorn backend.main:app --host 0.0.0.0 --port 8888 --workers 2 > server.log 2>&1 &
```

### 5. 访问

🌐 **公网地址**: **http://106.13.186.155:8078**

> ⚠️ 常见问题：连接失败先检查内存 `free -h`，90%+ 是内存溢出导致。

## 📱 功能演示

### 场景一：文本问答
> 用户："借阅规则是什么？"  
> 吉小图："本科生最多可借10册，借期30天，可续借1次..."

### 场景二：拍照导航（核心亮点）
> 用户：📸 拍一张书架照片  
> 吉小图："根据照片中的索书号 I247.5，您当前在**2F文学区推荐书架**。需要导航去其他地方吗？"

### 场景三：路径规划
> 用户："怎么去期刊阅览室？"  
> 吉小图："您现在在2F文学区 → 直走到电梯 → 上3F → 出电梯右转到底 → 🎯 到达期刊阅览室！"

## 🎥 演示视频脚本（90秒）

| 时间 | 内容 |
|------|------|
| 0:00-0:15 | 打开页面，展示欢迎界面 |
| 0:15-0:40 | 文本提问"图书馆开放时间是？"→ 获得准确回复 |
| 0:40-1:10 | 拍照识别书架 → AI识别出"2F文学区" |
| 1:10-1:30 | 请求导航到"期刊阅览室"→ 获得路径指引 |

## 📋 项目结构

```
├── README.md                   # 本文件
├── docs/                       # 项目文档
│   ├── 项目说明文档.md          # ≥600字详细说明
│   ├── 部署说明.md             # DGX Spark部署步骤
│   ├── 技术栈说明.md           # 技术组件详解
│   └── 十日谈.md               # 开发历程征文
├── backend/
│   ├── main.py                 # FastAPI入口
│   ├── config.py               # 配置管理
│   ├── agents/                 # Multi-Agent系统
│   │   ├── orchestrator.py     # 编排器（核心）
│   │   ├── guide_agent.py      # 导览Agent
│   │   ├── search_agent.py     # 检索Agent
│   │   ├── planning_agent.py   # 规划Agent
│   │   └── verify_agent.py     # 校验Agent
│   ├── knowledge/              # 知识库
│   │   ├── rag_pipeline.py     # RAG管道
│   │   ├── vector_store.py     # ChromaDB封装
│   │   ├── data_loader.py      # 数据加载器
│   │   └── data/               # JSON数据文件
│   └── models/                 # 模型层
│       └── stepfun_client.py   # Step 3.7 Flash API
├── frontend/                   # 移动端前端
│   ├── index.html
│   ├── css/style.css
│   └── js/
└── scripts/
    └── build_kb.py             # 知识库构建脚本
```

## 👥 团队

- **团队名称**：吉利学院图书馆团队
- **单位**：吉利学院图书馆
- **团队成员**：杨博，杨帅，高智洪

---

*本项目为 2026 DGX Spark Hackathon 参赛作品，基于 NVIDIA DGX Spark × Stepfun 阶跃星辰平台构建。*
