# 面向大学生普法教育的数字人智能问答交互系统

本系统是一款面向大学生普法教育场景的智能交互应用。集成了 RAG (Retrieval-Augmented Generation) 法律问答、引用依据追溯、案件情景模拟、TTS 语音合成以及 Unity WebGL 数字人播报，旨在通过数字人交互形式提供沉浸式的法律知识普及体验。

## 核心功能

- **法律问答与 RAG 检索**：支持大学生常见法律问题咨询，自动检索知识库并生成带有引用依据（Citation）的回答。
- **引用依据追溯**：在回答中提供具体的法律条文引用，点击可查看引用详情，增强权威性。
- **领域外拒答**：精准识别非法律领域问题（如娱乐、编程、股票预测等）并礼貌拒答。
- **查询扩展（Query Expansion）**：针对短查询（如“房东不退押金”）进行语义补全，提高检索准确度。
- **案件情景模拟**：提供交互式法律案件模拟流程，引导用户通过对话形式完成案情梳理并获得模拟判决。
- **TTS 语音合成**：实时将文本转化为语音，配合数字人播报。
- **Unity WebGL 数字人交互**：数字人支持口型同步、面部表情、肢体动作切换，增强交互沉浸感。
- **系统评测**：内置自动化评测脚本，可一键导出论文所需的 KPI 指标（响应率、引用准确率、领域过滤率等）。

## 技术栈

- **前端**：Vue 3, Vite, Element Plus, Pinia, Axios, Tailwind CSS
- **后端**：FastAPI, Uvicorn, SQLite (业务数据), Qdrant (向量存储)
- **数字人**：Unity WebGL, Animator, BlendShape, JavaScript Bridge
- **LLM/Embedding**：基于火山引擎 (Volcengine/Doubao) 的大模型接口
- **部署/评测**：Docker, Docker Compose, Pytest

## 目录结构

```text
.
├── backend/            # FastAPI 后端源码
├── frontend/           # Vue 3 前端源码
├── data/               # 知识库、数据库及静态资源（本地忽略，需按需初始化）
├── unity/              # Unity 源码工程（C#）
├── tools/              # 辅助工具（如反向代理等）
├── docker-compose.yml  # Docker 编排配置
└── README.md
```

## 快速开始

### 1. 环境准备

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose (可选)

### 2. 后端配置与运行

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env  # 并填写你的 API Key
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 前端配置与运行

```bash
cd frontend
npm install
npm run dev
```
访问 `http://localhost:5173` 即可进入系统。

### 4. 数据初始化与知识库构建

由于法律条文知识库体积较大，GitHub 仓库仅包含示例代码，需手动初始化：

1. **准备原始数据**：将法律条文 Markdown 文件放入 `data/laws_raw/`。
2. **运行导入脚本**：
   ```bash
   cd backend
   python scripts/ingest_just_laws.py
   ```
   该脚本会解析法律条文，生成向量并存入 Qdrant，同时在 `data/knowledge.db` 中建立索引。

### 5. Docker 部署

```bash
docker-compose up -d
```
系统将自动构建并启动前端 (80 端口) 与后端 (8000 端口)。

## 系统评测

本项目包含一套完整的自动化评测脚本，用于导出论文 KPI 指标：

```bash
cd backend
# 确保 .env 配置正确
python scripts/run_final_thesis_eval.py
```
评测报告将生成在 `backend/tests/reports/final_thesis_eval_report.md`。

## 声明

本项目为毕业设计作品，法律知识库仅供参考，不构成专业法律建议。

## License

MIT
