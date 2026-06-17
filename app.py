# -*- coding: utf-8 -*-
"""FastAPI 后端。

提供 REST + SSE 流式接口，串联五大智能体、LangGraph 工作流、
RAG 题库、代码沙箱与学习进度，并托管前端静态页面。

启动：  python -m uvicorn app:app --reload --port 8000
"""
import json

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from core import agents, progress, sandbox
from core.llm import get_llm
from core.rag import get_bank
from core.workflow import run_analysis_stream, run_eval_stream

app = FastAPI(title="算法竞赛辅导智能体")

progress.init_db()


def sse(obj):
    """格式化为一条 SSE 消息。"""
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


# ------------------------- 请求模型 -------------------------
class AnalyzeReq(BaseModel):
    problem: str


class EvaluateReq(BaseModel):
    problem: str
    code: str
    language: str = "python"
    problem_title: str = ""
    problem_type: str = "其他"
    difficulty: str = "未知"


class HintReq(BaseModel):
    problem: str
    analysis: dict = {}
    question: str = ""
    hint_level: int = 1
    history: str = ""


class ChatReq(BaseModel):
    problem: str = ""
    question: str
    history: list = []


class RunReq(BaseModel):
    code: str
    stdin: str = ""


# ------------------------- 题库 -------------------------
@app.get("/api/problems")
def list_problems():
    return get_bank().list_all()


@app.get("/api/problems/{pid}")
def get_problem(pid: str):
    p = get_bank().get(pid)
    return p or JSONResponse({"error": "not found"}, status_code=404)


# ------------------------- 分析流（SSE） -------------------------
@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    def gen():
        yield sse({"event": "start", "pipeline": ["retrieve", "analyze", "plan"]})
        try:
            for node, delta in run_analysis_stream(req.problem):
                yield sse({"event": "node", "node": node, "data": delta})
            yield sse({"event": "done"})
        except Exception as e:
            yield sse({"event": "error", "message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------- 评测流（SSE） -------------------------
@app.post("/api/evaluate")
def evaluate(req: EvaluateReq):
    def gen():
        yield sse({"event": "start",
                   "pipeline": ["review", "gen_tests", "run_tests", "summarize"]})
        summary = None
        try:
            for node, delta in run_eval_stream(
                req.problem, req.code, req.language,
                problem_title=req.problem_title,
                problem_type=req.problem_type,
                difficulty=req.difficulty,
            ):
                if node == "summarize":
                    summary = delta.get("summary")
                yield sse({"event": "node", "node": node, "data": delta})
            # 记录学习进度
            if summary:
                progress.record(
                    req.problem_title or "未命名", req.problem_type, req.difficulty,
                    passed=summary.get("passed", 0) == summary.get("total", 0)
                    and summary.get("total", 0) > 0,
                    tests_passed=summary.get("passed", 0),
                    tests_total=summary.get("total", 0),
                    score=summary.get("final_score", 0),
                    error_kind=summary.get("error_kind", "AC"),
                )
            yield sse({"event": "done"})
        except Exception as e:
            yield sse({"event": "error", "message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------- 苏格拉底提示（SSE 流式 token） -------------------------
@app.post("/api/hint")
def hint(req: HintReq):
    def gen():
        yield sse({"event": "start", "hint_level": req.hint_level})
        try:
            for chunk in agents.tutor_stream(
                req.problem, req.analysis, req.question,
                req.hint_level, req.history,
            ):
                text = getattr(chunk, "content", "") or ""
                if text:
                    yield sse({"event": "token", "text": text})
            yield sse({"event": "done"})
        except Exception as e:
            yield sse({"event": "error", "message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------- 自由对话（SSE 流式 token） -------------------------
CHAT_SYS = (
    "你是一位友好、专业的算法竞赛辅导老师。结合当前题目为学生答疑，"
    "讲解清晰、循循善诱。可以解释概念、纠正误区、点拨思路，"
    "但若学生还没认真思考就索要完整答案，要先鼓励其尝试。用中文回答。"
)


@app.post("/api/chat")
def chat(req: ChatReq):
    def gen():
        yield sse({"event": "start"})
        try:
            msgs = [("system", CHAT_SYS)]
            if req.problem:
                msgs.append(("system", "当前题目：\n" + req.problem))
            for m in req.history[-6:]:
                role = "assistant" if m.get("role") == "assistant" else "user"
                msgs.append((role, m.get("content", "")))
            msgs.append(("user", req.question))
            llm = get_llm(temperature=0.6, streaming=True, max_tokens=900)
            for chunk in llm.stream(msgs):
                text = getattr(chunk, "content", "") or ""
                if text:
                    yield sse({"event": "token", "text": text})
            yield sse({"event": "done"})
        except Exception as e:
            yield sse({"event": "error", "message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------- 直接运行代码（自定义输入） -------------------------
@app.post("/api/run")
def run_code(req: RunReq):
    return sandbox.run_python(req.code, req.stdin)


# ------------------------- 学习进度仪表盘 -------------------------
@app.get("/api/stats")
def get_stats():
    return progress.stats()


# ------------------------- 前端静态资源 -------------------------
@app.get("/")
def index():
    return FileResponse(settings.STATIC_DIR + "/index.html")


app.mount("/", StaticFiles(directory=settings.STATIC_DIR), name="static")
