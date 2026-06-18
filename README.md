# ⚔️ ARENA · 算法竞赛辅导智能体

> 一个基于**多智能体协作**的算法竞赛辅导系统。学生提交一道算法题，一支「AI 教练团队」协同完成：
> 题目分析 → 策略规划 → 苏格拉底式引导 → 代码审查 → 自动判题，并持续刻画用户画像、**因材施教**。

**在线体验**：<https://cp-tutor-agent.onrender.com>　|　**源码**：<https://github.com/ProZhang-Gr/cp-tutor-agent>

> 校企实训选题《项目 05 · 编程竞赛辅导智能体》的进阶 Web 实现。
> 首次打开若较慢，是免费云服务休眠后的冷启动（约 50 秒），稍候即可。

`FastAPI` · `LangGraph` · `LangChain` · `DeepSeek` · `Monaco` · `SSE 流式` · `Docker`

---

## ✨ 功能特性

### 1. 多智能体协作团队
系统把辅导拆给一支各司其职的智能体团队，前端可**实时看到每个智能体的工作状态**（待命 / 工作中 / 完成）：

| 智能体 | 职责 | 产出 |
|--------|------|------|
| 🔍 题库检索官 | RAG 相似题检索 | 从题库召回最相关的历史题，举一反三 |
| 🧠 题目分析师 | 拆解题目本质 | 题型、难度、目标复杂度、核心突破口、易错点、知识点 |
| 🗺️ 策略规划师 | 解法谱系 | 多种解法 + 时空复杂度 + 推荐指数 + 适用场景 |
| 🎓 苏格拉底导师 | 分层引导 | 4 层递进式提示，引导而非直接给答案 |
| 🔬 代码审查师 | 静态审查 | bug 定位、复杂度判断、优化建议、综合评分 |
| 🧪 测试生成师 | 构造用例 | 覆盖样例 / 边界 / 特殊 / 压力的测试用例 |

### 2. 两条 LangGraph 工作流
用状态机编排多步骤流程，含条件分支：

- **分析流**：`检索 → 分析 → 规划`
- **评测流**：`代码审查 →（语法不过则跳过）→ 生成用例 → 沙箱判题 → 汇总评分`

### 3. 真实代码沙箱判题
在隔离子进程中运行学生代码，喂入测试输入、比对输出，给出 **AC / WA / TLE / RE / CE** 判题结果与综合得分——不是「看起来能跑」，而是真的跑。

### 4. 苏格拉底式分层提示
卡住时逐层求助，4 层由浅入深：方向启发 → 突破口 → 核心思路 → 框架伪代码。**严格按层级把控信息量，不越级泄底**，培养独立思考。

### 5. 用户系统 + 因材施教 🎯
- **游客优先**：不登录也能用全部核心功能；登录后才记录历史、解锁个性化。
- **用户画像**：从答题历史自动刻画水平**档位**（新手 / 进阶 / 高手）与强弱题型。
- **因材施教**：导师与对话的策略随画像自适应——
  - 新手：更多脚手架、更早更具体的提示、更多鼓励；
  - 进阶：提示精炼、多用反问、适度提高挑战；
  - 高手：简洁犀利、主动抛出更优复杂度或更难变式；
  - 针对薄弱题型主动多加引导。
  > 注意：变的是**教学策略与挑战强度**，对每位学生始终保持尊重与鼓励，绝非「看人下菜碟」。

### 6. 学习数据仪表盘
按用户统计：总提交 / 通过率 / 平均分、各题型**掌握度雷达图**、判题结果分布、薄弱题型、近期记录。

### 7. 人性化交互
- 左右栏**可拖动调宽 / 一键折叠**，专注写代码时把屏幕让给编辑器；
- **刷新不丢**：题目与代码自动存本地；
- **快捷键**：`Ctrl+Enter` 运行、`Ctrl+S` 提交；
- Monaco（VS Code 同款）编辑器、流式打字机输出、智能体协作动画。

### 8. 用户系统 · 会员分级 · 每日报告（企业级）
- **账号体系**：注册/登录（密码加盐哈希、HMAC 签名 Cookie），游客优先、数据按用户隔离；
- **Free / Pro 分级**：算力点 `credits` 体系，模拟充值即开通 Pro（不接真钱）；
  - Pro 解锁：**不受每日额度** · **深度分析**（额外解题推演）· **每日报告 PDF 下载**；
- **AI 每日学习报告**：聚合当日刷题数据 + LLM 叙述性点评 + 明日建议，一键导出中文 PDF；
- **防滥用**：IP 限流 + 每日配额 + 审计日志 + 输入上限 + 对话话题守门（给 API 花费封顶）；
- **数据持久层**：SQLAlchemy 2.0 ORM + 连接池 + Alembic 迁移，本地 SQLite / 线上 PostgreSQL(Neon) 透明切换。

---

## 🧠 技术栈

| 层 | 技术 | 用途与选型理由 |
|----|------|----------------|
| Web 框架 | **FastAPI** + Uvicorn | 异步、类型友好；同步阻塞的 LLM 调用由 Starlette 自动放进线程池，不阻塞事件循环 |
| 实时流式 | **SSE**（Server-Sent Events） | 逐 token 推送导师回答、逐节点推送智能体进度，前端用 fetch + ReadableStream 解析 |
| 大模型 | **DeepSeek**（`deepseek-chat`） | OpenAI 兼容协议，中文与代码推理强、成本低；结构化输出走 JSON 模式 |
| 工作流编排 | **LangGraph** | 用状态机（StateGraph）编排多智能体多步骤流程，含条件分支；`stream` 驱动前端可视化 |
| LLM 框架 | **LangChain** | Prompt 模板、消息组装、链式调用；接 `ChatOpenAI` 走 DeepSeek |
| 检索增强 | **LangChain TFIDFRetriever** | 题库 RAG，底层 scikit-learn，**零模型下载**、开箱即用；中文用字符级 n-gram 规避分词依赖 |
| 代码沙箱 | **subprocess** 隔离 | 独立子进程 + 超时控制 + 临时工作目录；**剥离环境变量**防密钥泄露 |
| 数据持久层 | **SQLAlchemy 2.0** + **Alembic** | ORM + 连接池 + 版本化迁移；本地 SQLite、线上 PostgreSQL(Neon) 透明切换 |
| 报告导出 | **reportlab** | 每日报告 PDF，内置中文字体（STSong），无需外部字体文件 |
| 认证 | **pbkdf2 + HMAC** | 密码加盐哈希（标准库）、HMAC 签名 Cookie 实现无状态登录、防篡改 |
| 前端 | 原生 **JS** + **Monaco** + **Chart.js** + **marked** | 无框架、零构建；Monaco 编辑器、Chart.js 图表、marked 渲染 Markdown |
| 设计 | **Fraunces** / IBM Plex Sans / JetBrains Mono | 暖色「书桌」主题，衬线标题 + 无衬线正文 + 等宽代码；字体走 jsdelivr/@fontsource（国内可达） |
| 部署 | **Docker** + Render | 单一 Dockerfile 适配 Render（`$PORT`）与 Hugging Face Spaces（7860） |

---

## 🏗️ 系统架构

```
                          浏览器（原生 JS · Monaco · SSE）
                                    │  REST / SSE
                                    ▼
┌─────────────────────────  FastAPI 后端  ─────────────────────────┐
│  认证 (pbkdf2+HMAC Cookie)   ·   用户画像 / 因材施教指令          │
│                                                                  │
│   分析流 (LangGraph)            评测流 (LangGraph)                │
│   检索→分析→规划                审查→[分支]→生成用例→判题→汇总     │
│      │                              │                            │
│      ▼                              ▼                            │
│  五大智能体 (LangChain → DeepSeek)        代码沙箱 (subprocess)   │
│      │                                                           │
│  RAG 题库 (TFIDF)                 进度/用户 (SQLite / Postgres)   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

```
算法竞赛辅导智能体/
├── app.py              FastAPI 后端：REST + SSE + 认证端点
├── config.py           配置：密钥(env/文件)、模型、路径、SECRET_KEY、DATABASE_URL
├── run.py              一键启动：开浏览器、打印局域网地址
├── start.bat           Windows 双击启动
├── Dockerfile          云部署镜像（端口自适应 $PORT / 7860）
├── render.yaml         Render 部署蓝图
├── core/
│   ├── llm.py          DeepSeek LLM 工厂 + JSON 解析
│   ├── agents.py       五大智能体（提示词 + 调用）
│   ├── workflow.py     LangGraph 两条工作流
│   ├── rag.py          LangChain RAG 题库
│   ├── sandbox.py      代码执行沙箱 + 判题（环境变量隔离）
│   ├── db.py           数据库抽象层（SQLite / Postgres）
│   ├── auth.py         注册/登录/密码哈希/签名 Cookie
│   ├── profile.py      用户画像 + 因材施教指令
│   └── progress.py     按用户的学习进度统计
├── data/problems.json  题库（14 道经典题）
├── static/             前端（index.html / style.css / app.js）
└── requirements.txt
```

---

## 🚀 本地运行

```bash
pip install -r requirements.txt
```

配置 DeepSeek API Key（任选）：在同目录建 `.deepseek_key` 文件写入 key（已被 gitignore），或设环境变量 `DEEPSEEK_API_KEY`。

启动：双击 **`start.bat`**，或 `python run.py`，浏览器打开 <http://127.0.0.1:8000>。

---

## ☁️ 云部署（固定公网网址）

> 密钥只经平台**环境变量/Secret** 注入，绝不进仓库；沙箱已剥离子进程环境变量，访客无法读取密钥。

### Render（推荐）
1. 把项目推到 GitHub 仓库。
2. [render.com](https://render.com) → **New + → Web Service** → 选仓库（自动识别 `Dockerfile`）。
3. Instance Type 选 **Free**。
4. 在 **Environment** 添加变量：
   - `DEEPSEEK_API_KEY = sk-…`（必填）
   - `SECRET_KEY = 任意随机串`（建议，登录态签名）
   - `DATABASE_URL = postgres://…`（可选，持久化）
5. **Create Web Service**，得到 `https://xxx.onrender.com`。

> 免费版闲置 15 分钟休眠（冷启动约 50 秒）、内存 512MB。
> **数据持久化**：不设 `DATABASE_URL` 用 SQLite，重新部署会清空账号/历史；
> 想长期保存，去 [neon.tech](https://neon.tech) 免费开 Postgres，连接串填进 `DATABASE_URL`，代码自动切换。

### Hugging Face Spaces（备选，免 GitHub）
新建 Docker Space，README 顶部加 `sdk: docker` / `app_port: 7860` 配置头，网页上传文件，Secrets 里设 `DEEPSEEK_API_KEY`。

---

## 🔒 安全设计

- **密钥不进仓库**：本地 `.deepseek_key`（gitignore）/ 云端环境变量。
- **沙箱隔离**：学生代码在子进程运行，环境变量经白名单过滤，剥离 `DEEPSEEK_API_KEY` 等密钥，防止通过 `os.environ` 窃取。
- **密码安全**：pbkdf2-HMAC-SHA256 加盐哈希，不存明文；登录态用 HMAC 签名 Cookie，防篡改。

> 沙箱为教学用途的轻量隔离（子进程 + 超时 + 临时目录 + 环境过滤），未做系统调用级硬隔离；生产环境应换容器 / seccomp。

---

## 🧭 使用流程

1. **输入题目**：粘贴题面，或从题库选一道经典题。
2. **启动分析**：智能体团队依次点亮，给出题型/难度/突破口/策略谱系/相似题。
3. **编写代码**：Monaco 编辑器写解法，`Ctrl+Enter` 用自定义输入快速试跑。
4. **提交评测**：触发审查师 + 测试师，自动判题给分。
5. **求助导师**：逐层请求提示，或与导师自由对话。
6. **登录**：右上角注册/登录，记录历史、解锁因材施教。
7. **看仪表盘**：掌握度雷达图、薄弱题型、历史记录。
