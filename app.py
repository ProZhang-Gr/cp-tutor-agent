# -*- coding: utf-8 -*-
"""FastAPI 后端。

提供 REST + SSE 流式接口，串联五大智能体、LangGraph 工作流、
RAG 题库、代码沙箱与学习进度，并托管前端静态页面。

启动：  python -m uvicorn app:app --reload --port 8000
"""
import json
import os

from fastapi import Cookie, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from core import agents, auth, billing, guard, profile, progress, report, sandbox
from core.llm import get_llm
from core.rag import get_bank
from core.debugger import run_debug_stream
from core.workflow import run_analysis_stream, run_eval_stream

app = FastAPI(title="算法竞赛辅导智能体")


def _init_db():
    """启动时将数据库迁移到最新版本；迁移不可用时回退到按模型建表。"""
    try:
        from alembic import command
        from alembic.config import Config
        cfg = Config(os.path.join(settings.ROOT, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(settings.ROOT, "migrations"))
        command.upgrade(cfg, "head")
    except Exception as e:  # 迁移异常不应阻断启动
        print("[db] alembic upgrade 失败(%s)，回退 create_all" % e)
        from core.db import create_all
        create_all()


_init_db()

COOKIE = "arena_session"


@app.middleware("http")
async def no_cache_assets(request, call_next):
    """让浏览器每次都向服务器校验前端资源，避免改版后用到旧缓存导致布局错乱。"""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".css", ".js", ".html")):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


def sse(obj):
    """格式化为一条 SSE 消息。"""
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _uid(session):
    """从登录 Cookie 解出用户 id；游客返回 None。"""
    return auth.parse_token(session) if session else None


def _ip(request):
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _abuse_block(request, uid, endpoint):
    """限流/配额守门：放行返回 None，拦截返回 429 响应。

    Pro（credits>0）不受每日配额限制，但每次调用消耗 1 算力点；
    余额耗尽或普通用户则走每日配额。限流与审计对所有人生效。
    """
    ip = _ip(request)
    if billing.get_status(uid)["is_pro"] and billing.spend(uid, 1) is not None:
        ok, msg = guard.check_and_log(ip, uid, endpoint, is_pro=True)
    else:
        ok, msg = guard.check_and_log(ip, uid, endpoint, is_pro=False)
    return None if ok else JSONResponse({"error": msg}, status_code=429)


# ------------------------- 请求模型 -------------------------
class AnalyzeReq(BaseModel):
    problem: str
    deep: bool = False   # Pro 深度分析（额外输出解题推演）


class EvaluateReq(BaseModel):
    problem: str
    code: str
    language: str = "python"
    problem_id: str = ""
    problem_title: str = ""
    problem_type: str = "其他"
    difficulty: str = "未知"


class SaveProblemReq(BaseModel):
    title: str
    type: str = "其他"
    difficulty: str = "未知"
    description: str


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
    code: str = ""        # 学生编辑器里的完整代码（导师可实时看到）
    selection: str = ""   # 学生框选、想重点询问的片段


class RunReq(BaseModel):
    code: str
    stdin: str = ""


class DebugReq(BaseModel):
    problem: str = ""
    code: str
    counterexample: dict = {}  # {input, expected, actual, reason}


class AuthReq(BaseModel):
    username: str
    password: str


# ------------------------- 认证 -------------------------
def _set_login(resp, uid):
    token = auth.make_token(uid)
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=30 * 24 * 3600)


@app.post("/api/register")
def register(req: AuthReq, resp: Response):
    err = auth.validate_credentials(req.username, req.password)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    user, err = auth.create_user(req.username, req.password)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    _set_login(resp, user["id"])
    return {"user": user}


@app.post("/api/login")
def login(req: AuthReq, resp: Response):
    user = auth.authenticate(req.username, req.password)
    if not user:
        return JSONResponse({"error": "用户名或密码错误"}, status_code=401)
    _set_login(resp, user["id"])
    return {"user": user}


@app.post("/api/logout")
def logout(resp: Response):
    resp.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if uid is None:
        return {"user": None, "profile": profile.build_profile(None), "billing": billing.get_status(None)}
    user = auth.get_user_by_id(uid)
    if not user:
        return {"user": None, "profile": profile.build_profile(None), "billing": billing.get_status(None)}
    return {"user": {"id": user["id"], "username": user["username"]},
            "profile": profile.build_profile(uid),
            "billing": billing.get_status(uid)}


class RechargeReq(BaseModel):
    yuan: int = 10


@app.post("/api/recharge")
def recharge(req: RechargeReq, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if uid is None:
        return JSONResponse({"error": "请先登录再充值"}, status_code=401)
    bal = billing.recharge(uid, req.yuan)
    return {"credits": bal, "is_pro": (bal or 0) > 0}


# ------------------------- 题库 -------------------------
@app.get("/api/problems")
def list_problems():
    return get_bank().list_all()


@app.get("/api/problems/{pid}")
def get_problem(pid: str, arena_session: str = Cookie(default=None)):
    if pid.startswith("U"):                       # 用户自建题
        p = progress.get_user_problem(_uid(arena_session), pid)
    else:
        p = get_bank().get(pid)
    return p or JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/my-problems")
def my_problems(arena_session: str = Cookie(default=None)):
    return progress.list_user_problems(_uid(arena_session))


@app.get("/api/solved")
def solved(arena_session: str = Cookie(default=None)):
    return {"solved": progress.solved_problem_ids(_uid(arena_session))}


@app.post("/api/save-problem")
def save_problem(req: SaveProblemReq, arena_session: str = Cookie(default=None)):
    pid = progress.add_user_problem(_uid(arena_session), req.title,
                                    req.type, req.difficulty, req.description)
    return {"id": pid}


# ------------------------- 分析流（SSE） -------------------------
@app.post("/api/analyze")
def analyze(req: AnalyzeReq, request: Request, arena_session: str = Cookie(default=None)):
    if len(req.problem) > settings.MAX_PROBLEM_CHARS:
        return JSONResponse({"error": "题面过长（上限 %d 字）" % settings.MAX_PROBLEM_CHARS}, status_code=400)
    uid = _uid(arena_session)
    blocked = _abuse_block(request, uid, "analyze")
    if blocked:
        return blocked
    deep = bool(req.deep) and billing.get_status(uid)["is_pro"]   # 深度分析仅 Pro 可用

    def gen():
        yield sse({"event": "start", "pipeline": ["retrieve", "analyze", "plan"]})
        try:
            for node, delta in run_analysis_stream(req.problem, deep=deep):
                yield sse({"event": "node", "node": node, "data": delta})
            yield sse({"event": "done"})
        except Exception as e:
            yield sse({"event": "error", "message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------- 评测流（SSE） -------------------------
@app.post("/api/evaluate")
def evaluate(req: EvaluateReq, request: Request, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if len(req.problem) > settings.MAX_PROBLEM_CHARS or len(req.code) > settings.MAX_CODE_CHARS:
        return JSONResponse({"error": "题面或代码过长"}, status_code=400)
    blocked = _abuse_block(request, uid, "evaluate")
    if blocked:
        return blocked

    def gen():
        yield sse({"event": "start",
                   "pipeline": ["review", "judge", "summarize"]})
        summary = None
        try:
            for node, delta in run_eval_stream(
                req.problem, req.code, req.language,
                problem_id=req.problem_id or None,
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
                    user_id=uid,
                    problem_id=req.problem_id or None,
                )
            yield sse({"event": "done"})
        except Exception as e:
            yield sse({"event": "error", "message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------- Agentic 调试回路（SSE） -------------------------
@app.post("/api/debug")
def debug(req: DebugReq, request: Request, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if len(req.code) > settings.MAX_CODE_CHARS or len(req.problem) > settings.MAX_PROBLEM_CHARS:
        return JSONResponse({"error": "题面或代码过长"}, status_code=400)
    blocked = _abuse_block(request, uid, "debug")
    if blocked:
        return blocked

    def gen():
        yield sse({"event": "start"})
        try:
            for kind, payload in run_debug_stream(req.problem, req.code, req.counterexample):
                yield sse({"event": kind, "data": payload})
            yield sse({"event": "done"})
        except Exception as e:
            yield sse({"event": "error", "message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream")


# ------------------------- 苏格拉底提示（SSE 流式 token） -------------------------
@app.post("/api/hint")
def hint(req: HintReq, request: Request, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if len(req.problem) > settings.MAX_PROBLEM_CHARS:
        return JSONResponse({"error": "题面过长"}, status_code=400)
    blocked = _abuse_block(request, uid, "hint")
    if blocked:
        return blocked
    directive = profile.build_directive(uid)

    def gen():
        yield sse({"event": "start", "hint_level": req.hint_level})
        try:
            for chunk in agents.tutor_stream(
                req.problem, req.analysis, req.question,
                req.hint_level, req.history, directive,
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
    "你是一位友好、博学、健谈的算法与编程辅导老师。"
    "当学生询问某个技术点、算法概念或原理（如「什么是动态规划」「Dijkstra 为什么要用堆」），"
    "请热情、清晰、有条理地讲解，可举例、可类比，并欢迎他继续追问、闲聊式地深入这个话题。"
    "只有当学生是在求解某道具体题目、且还没认真思考就想直接要完整答案时，才先点拨思路、鼓励其尝试，不和盘托出。"
    "你只讨论编程、算法、计算机科学相关话题；若用户问与此无关的内容（闲聊八卦、其他学科、"
    "或想把你当通用写作/翻译工具），请礼貌婉拒并把话题引回算法学习，不要展开作答。"
    "用中文回答，语气亲切自然。"
)


@app.post("/api/chat")
def chat(req: ChatReq, request: Request, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if len(req.question) > settings.MAX_QUESTION_CHARS or len(req.code) > settings.MAX_CODE_CHARS:
        return JSONResponse({"error": "输入过长"}, status_code=400)
    blocked = _abuse_block(request, uid, "chat")
    if blocked:
        return blocked
    directive = profile.build_directive(uid)

    def gen():
        yield sse({"event": "start"})
        try:
            msgs = [("system", CHAT_SYS)]
            if directive:
                msgs.append(("system", "因材施教：" + directive))
            if req.problem:
                msgs.append(("system", "当前题目：\n" + req.problem))
            if req.code.strip():
                msgs.append(("system", "学生当前编辑器里的完整代码（请结合它来回答，"
                                       "可直接引用具体行/变量）：\n```python\n"
                                       + req.code[:4000] + "\n```"))
            if req.selection.strip():
                msgs.append(("system", "学生用鼠标框选、想重点询问的代码片段：\n```python\n"
                                       + req.selection[:2000] + "\n```"))
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
def get_stats(arena_session: str = Cookie(default=None)):
    return progress.stats(_uid(arena_session))


# ------------------------- 每日报告（Pro） -------------------------
class ReportPdfReq(BaseModel):
    date: str = ""
    narrative: str = ""
    stats: dict = {}


def _pro_or_block(uid):
    if uid is None:
        return JSONResponse({"error": "请先登录"}, status_code=401)
    if not billing.get_status(uid)["is_pro"]:
        return JSONResponse({"error": "每日报告是 Pro 功能，充值即可解锁"}, status_code=403)
    return None


@app.get("/api/daily-report")
def daily_report(arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    block = _pro_or_block(uid)
    if block:
        return block
    return report.build_report(uid)


@app.post("/api/daily-report/pdf")
def daily_report_pdf(req: ReportPdfReq, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    block = _pro_or_block(uid)
    if block:
        return block
    user = auth.get_user_by_id(uid)
    pdf = report.build_pdf(
        {"date": req.date, "narrative": req.narrative, "stats": req.stats},
        user["username"] if user else "")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=arena_daily_report.pdf"})


# ------------------------- 前端静态资源 -------------------------
@app.get("/")
def index():
    return FileResponse(settings.STATIC_DIR + "/index.html")


app.mount("/", StaticFiles(directory=settings.STATIC_DIR), name="static")
