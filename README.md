# ⚔️ 算法竞赛辅导智能体 (CP-Tutor Agent)

一个基于 **多智能体协作** 的算法竞赛辅导 Web 系统。学生提交题目，系统用一支
"AI 教练团队" 完成：题目分析 → 策略规划 → 苏格拉底式引导 → 代码审查 → 自动判题，
并持续追踪学习进度、分析薄弱点。

> 校企实训 · 项目 05《编程竞赛辅导智能体》的进阶实现（Web 版）。

---

## ✨ 核心特性

| 模块 | 技术 | 说明 |
|------|------|------|
| 五大智能体 | LLM (DeepSeek) | 分析师 / 规划师 / 苏格拉底导师 / 审查师 / 测试师，各司其职 |
| 工作流编排 | **LangGraph** | 两条状态机：分析流（检索→分析→规划）、评测流（审查→生成用例→判题→汇总），含条件分支 |
| RAG 题库 | **LangChain** TFIDFRetriever | 相似题检索，"举一反三"，零模型下载、开箱即用 |
| 代码沙箱 | subprocess 隔离 | 真实运行代码、喂入用例、超时控制、AC/WA/TLE/RE/CE 判题 |
| 学习分析 | SQLite + Chart.js | 通过率、题型掌握度雷达图、判题分布、薄弱点 |
| 交互界面 | Monaco + SSE | VS Code 同款编辑器、智能体协作实时可视化、流式打字机输出 |

设计要求全覆盖：✅ LangChain RAG 题库　✅ LangGraph 多步骤流程　✅ 友好交互界面（代码编辑+运行）　✅ 学习进度与错误分析。

---

## 🚀 本地运行

依赖（已在 Python 3.12 验证）：

```bash
pip install -r requirements.txt
```

API Key 配置（任选其一）：
- 在同目录新建 `.deepseek_key` 文件，把 key 写进去（已被 `.gitignore` 忽略，不进仓库）；
- 或设环境变量：`set DEEPSEEK_API_KEY=sk-xxx`（Windows）。

启动（Windows 一键）：双击 **`start.bat`**，或：

```bash
python run.py          # 自动开浏览器，打印局域网访问地址
```

浏览器打开 **http://127.0.0.1:8000**

---

## ☁️ 云部署（固定公网网址）

> 安全前提：密钥只通过平台 **环境变量/Secret** 注入，**绝不提交进仓库**；代码沙箱已剥离子进程环境变量，访客无法读取密钥。

### 方案 A · Render（推荐，走 GitHub）

1. 把本项目推到一个 GitHub 仓库（确认 `.deepseek_key` 没被提交）。
2. 登录 [render.com](https://render.com)（可用 GitHub 账号登录）。
3. **New + → Web Service**，连接该仓库；Render 会自动识别 `Dockerfile`（或 `render.yaml`）。
4. Instance Type 选 **Free**。
5. 在 **Environment** 添加变量：`DEEPSEEK_API_KEY = sk-你的key`。
6. **Create Web Service**，等构建完成，得到 `https://xxx.onrender.com`。

> 免费版闲置 15 分钟会休眠，下次打开冷启动约 30–50 秒；内存 512MB，本项目够用但偏紧。
> Render 运行时会注入 `$PORT`，Dockerfile 已自动适配。

### 方案 B · Hugging Face Spaces（免 GitHub，可网页上传）

1. 注册 [huggingface.co](https://huggingface.co) → **New Space** → SDK 选 **Docker** → 选 Blank。
2. 在 README.md **最顶部**加入下面的配置头（HF 据此识别端口）：
   ```yaml
   ---
   title: 算法竞赛辅导智能体
   emoji: ⚔️
   colorFrom: green
   colorTo: yellow
   sdk: docker
   app_port: 7860
   ---
   ```
3. 把项目文件全部上传（网页可直接拖拽；**不要传 `.deepseek_key`**）。
4. Space **Settings → Variables and secrets** 添加 Secret：`DEEPSEEK_API_KEY`。
5. 等待自动构建，得到 `https://用户名-空间名.hf.space`。

---

## 🧭 使用流程

1. **输入题目**：粘贴题面，或右上角「从题库选择」一道经典题。
2. **启动分析**：点「🚀 启动智能体分析」，右侧智能体团队依次点亮，左栏给出题型/难度/突破口/易错点/解题策略谱系/相似题。
3. **编写代码**：中间 Monaco 编辑器写解法，「▶ 运行」可用自定义输入快速试跑。
4. **提交评测**：「✅ 提交评测」触发审查师+测试师，自动生成用例并判题，给出综合得分。
5. **求助导师**：卡住时点「💡 请求下一层提示」获取递进式启发（共 4 层，由浅入深），或直接和导师对话答疑。
6. **看仪表盘**：切到「📊 学习仪表盘」查看掌握度雷达图、薄弱题型与历史记录。

---

## 📁 项目结构

```
算法竞赛辅导智能体/
├── app.py              FastAPI 后端（REST + SSE 流式）
├── config.py           配置（API/模型/路径）
├── core/
│   ├── llm.py          DeepSeek LLM 工厂 + JSON 解析
│   ├── agents.py       五大智能体（提示词 + 调用）
│   ├── workflow.py     LangGraph 两条工作流
│   ├── rag.py          LangChain RAG 题库
│   ├── sandbox.py      代码执行沙箱 + 判题
│   └── progress.py     SQLite 学习进度
├── data/
│   ├── problems.json   题库（14 道经典题）
│   └── progress.db     学习记录（运行后自动生成）
├── static/             前端（index.html / style.css / app.js）
└── requirements.txt
```

---

## ⚠️ 说明

- 代码沙箱为教学用途的轻量隔离（子进程 + 超时 + 临时目录），未做系统调用级硬隔离；生产环境应换容器/seccomp。
- 模型默认 `deepseek-chat`，结构化输出走 JSON 模式，导师对话/提示走流式输出。
