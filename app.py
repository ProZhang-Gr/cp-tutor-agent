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
from core import (admin, agents, auth, billing, community, guard, profile, progress,
                  report, sandbox, studyplan, support, telemetry, verify)
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
community.seed_if_empty()   # 社群空表时灌入引导帖，避免一打开就冷清

# 启动自检：缺 API Key 时醒目告警（不阻断启动，但首个 LLM 请求必然失败）
if not settings.DEEPSEEK_API_KEY:
    print("[startup] 警告：未检测到 DEEPSEEK_API_KEY（环境变量或 .deepseek_key 文件均为空），"
          "所有 LLM 功能将报错。请配置后重启。")

# 管理后台默认弱口令告警：仓库里写死的 manager/123456 是公开可见的，生产务必用
# 环境变量 ADMIN_USER / ADMIN_PASS 覆盖，否则任何人都能进 /admin 后台。
if admin.USING_DEFAULT_CREDS:
    print("[startup] 安全警告：管理后台仍在使用默认账号 manager/123456（公开仓库可见）！"
          "生产环境请在平台环境变量里设 ADMIN_USER / ADMIN_PASS 覆盖，并固定 SECRET_KEY。")

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


def _audit_meta(request):
    """收集供监控/取证的请求指纹：真实 socket 来源 + 原始 XFF 链 + UA。

    _ip() 取的是 XFF 最左值（可被客户端伪造），仅用于尽力识别；这里额外记下
    request.client.host（真正连到服务端的对端）与完整 XFF 链，便于事后核查。
    """
    peer = request.client.host if request.client else "?"
    ua = (request.headers.get("user-agent") or "")[:100]
    xff = request.headers.get("x-forwarded-for")
    parts = ["peer=" + peer]
    if xff:
        parts.append("xff=" + xff[:120])
    if ua:
        parts.append("ua=" + ua)
    return " | ".join(parts)


def _abuse_block(request, uid, endpoint):
    """限流/配额守门：放行返回 None，拦截返回 429 响应。

    顺序刻意是「先判限流/全站上限/配额，通过后再扣 Pro 算力点」——
    避免出现「被限流拦下却已白扣一点」。Pro（credits>0）不受每日配额，
    但每次成功调用消耗 1 算力点；限流、全站上限与审计对所有人生效。
    """
    ip = _ip(request)
    is_pro = billing.get_status(uid)["is_pro"]
    ok, msg = guard.check_and_log(ip, uid, endpoint, is_pro=is_pro, meta=_audit_meta(request))
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    if is_pro:
        billing.spend(uid, 1)   # 通过后再扣点
    return None


def _require_pro(uid):
    """高级能力（苏格拉底导师 / 导师对话 / 深度分析）需 Pro 算力点。

    非 Pro 返回 402，并带 PRO_REQUIRED 标记，供前端引导「看广告得点 / 充值」。
    导师审阅、普通智能体分析不走这里，对游客与普通用户免费开放。
    """
    if not billing.get_status(uid)["is_pro"]:
        return JSONResponse(
            {"error": "PRO_REQUIRED",
             "message": "该功能需算力点。看广告免费得点，或充值开通 Pro。"},
            status_code=402)
    return None


def _reward_community(request, uid, kind):
    """发帖 / 答疑后发放算力点激励，按日限次防刷。kind ∈ {'post','reply'}。

    用「答疑得点」把社群从单纯讨论区变成有正反馈的互助生态：你帮别人，
    平台用虚拟币回报你。返回本次实际发放的点数（达每日上限则为 0）。
    """
    if uid is None:
        return 0
    if kind == "post":
        cap, pts, ep = settings.POST_REWARD_DAILY, settings.POST_REWARD_POINTS, "reward_post"
    else:
        cap, pts, ep = settings.REPLY_REWARD_DAILY, settings.REPLY_REWARD_POINTS, "reward_reply"
    if guard.count_endpoint_today(uid, ep) >= cap:
        return 0
    if billing.grant(uid, pts) is None:
        return 0
    guard.log_event(uid, _ip(request), ep)
    return pts


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
    hints: str = ""       # 苏格拉底导师已给过的分层提示（供对话保持连贯）


class RunReq(BaseModel):
    code: str
    stdin: str = ""
    language: str = "python"


class ReviewCodeReq(BaseModel):
    problem: str = ""
    code: str
    language: str = "python"
    problem_id: str = ""   # 给了题目则用其真值/样例验证修订代码


class DebugReq(BaseModel):
    problem: str = ""
    code: str
    counterexample: dict = {}  # {input, expected, actual, reason}
    language: str = "python"


class VerifyReq(BaseModel):
    code: str
    language: str = "python"
    problem_id: str = ""   # 给了题目则用其真值/样例验证，否则只验证能否正常编译运行


class AuthReq(BaseModel):
    username: str
    password: str


# ------------------------- 认证 -------------------------
def _set_login(resp, uid):
    token = auth.make_token(uid)
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                    secure=settings.COOKIE_SECURE, max_age=30 * 24 * 3600)


@app.post("/api/register")
def register(req: AuthReq, request: Request, resp: Response):
    ok, msg = guard.rate_limit_only(_ip(request))   # 限流防注册轰炸
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    err = auth.validate_credentials(req.username, req.password)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    user, err = auth.create_user(req.username, req.password)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    _set_login(resp, user["id"])
    return {"user": user}


@app.post("/api/login")
def login(req: AuthReq, request: Request, resp: Response):
    ok, msg = guard.rate_limit_only(_ip(request))   # 限流防密码暴力破解
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    user = auth.authenticate(req.username, req.password)
    if not user:
        return JSONResponse({"error": "用户名或密码错误"}, status_code=401)
    _set_login(resp, user["id"])
    return {"user": user}


@app.post("/api/logout")
def logout(resp: Response):
    resp.delete_cookie(COOKIE)
    return {"ok": True}


class PwResetReq(BaseModel):
    username: str = ""
    contact: str = ""
    note: str = ""


@app.post("/api/password-reset")
def password_reset_request(req: PwResetReq, request: Request):
    """找回密码：提交一条「向管理员申请重置」工单（不接邮件，零外部依赖）。"""
    ok, msg = guard.rate_limit_only(_ip(request))   # 限流防刷工单
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    okk, m = support.create_request(req.username, req.contact, req.note)
    if not okk:
        return JSONResponse({"error": m}, status_code=400)
    return {"ok": True, "message": m}


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
            "billing": billing.get_status(uid),
            "checkin": {"today": guard.count_endpoint_today(uid, "checkin") > 0,
                        "points": settings.CHECKIN_POINTS}}


class RechargeReq(BaseModel):
    yuan: int = 10


@app.post("/api/recharge")
def recharge(req: RechargeReq, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if uid is None:
        return JSONResponse({"error": "请先登录再充值"}, status_code=401)
    # 模拟充值，但仍限额：单次 1~1000 元，防止自助刷出天量算力点再去打爆 LLM 花费
    try:
        yuan = int(req.yuan)
    except (TypeError, ValueError):
        yuan = 0
    if yuan < 1 or yuan > 1000:
        return JSONResponse({"error": "充值金额需在 1~1000 之间"}, status_code=400)
    bal = billing.recharge(uid, yuan)
    return {"credits": bal, "is_pro": (bal or 0) > 0}


@app.post("/api/ad-reward")
def ad_reward(request: Request, arena_session: str = Cookie(default=None)):
    """看完一段（模拟）激励广告后发放算力点。需登录，按日限次防滥用。"""
    uid = _uid(arena_session)
    if uid is None:
        return JSONResponse({"error": "请先登录再看广告领算力点"}, status_code=401)
    used = guard.count_endpoint_today(uid, "ad_reward")
    if used >= settings.AD_DAILY_LIMIT:
        return JSONResponse(
            {"error": "今日看广告次数已达上限（%d 次/天），明天再来或直接充值" % settings.AD_DAILY_LIMIT},
            status_code=429)
    bal = billing.grant(uid, settings.AD_REWARD_POINTS)
    if bal is None:
        return JSONResponse({"error": "发放失败，请重试"}, status_code=400)
    guard.log_event(uid, _ip(request), "ad_reward")
    return {"credits": bal, "gained": settings.AD_REWARD_POINTS,
            "remaining_today": max(0, settings.AD_DAILY_LIMIT - used - 1)}


# ------------------------- 每日签到（平台内激励） -------------------------
@app.post("/api/checkin")
def checkin(request: Request, arena_session: str = Cookie(default=None)):
    """每日签到发放算力点。需登录，每日仅一次（按审计端点计数判定）。"""
    uid = _uid(arena_session)
    if uid is None:
        return JSONResponse({"error": "请先登录再签到"}, status_code=401)
    if guard.count_endpoint_today(uid, "checkin") > 0:
        return JSONResponse({"error": "今天已经签到过了，明天再来～"}, status_code=409)
    bal = billing.grant(uid, settings.CHECKIN_POINTS)
    if bal is None:
        return JSONResponse({"error": "签到失败，请重试"}, status_code=400)
    guard.log_event(uid, _ip(request), "checkin")
    return {"credits": bal, "gained": settings.CHECKIN_POINTS}


# ------------------------- 学习行为埋点（聚合，非键鼠记录） -------------------------
class TelemetryReq(BaseModel):
    problem_id: str = ""
    active_seconds: int = 0
    keystrokes: int = 0
    runs: int = 0
    submits: int = 0


@app.post("/api/telemetry")
def telemetry_ingest(req: TelemetryReq, request: Request, arena_session: str = Cookie(default=None)):
    """接收聚合学习行为（时长 + 计数）。只限流、不计 LLM 配额；全 0 段静默忽略。"""
    ok, msg = guard.rate_limit_only(_ip(request))
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    saved = telemetry.record(_uid(arena_session), req.problem_id,
                             req.active_seconds, req.keystrokes, req.runs, req.submits)
    return {"ok": True, "saved": saved}


@app.get("/api/telemetry/summary")
def telemetry_summary(arena_session: str = Cookie(default=None)):
    return telemetry.summary(_uid(arena_session))


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


@app.get("/api/submissions")
def submissions(problem_id: str = "", arena_session: str = Cookie(default=None)):
    """某题的历次提交（含源代码），按时间倒序。"""
    return {"submissions": progress.list_submissions(_uid(arena_session), problem_id or None)}


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
                    code=req.code,
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
            dlang = req.language if req.language in settings.SUPPORTED_LANGS else "python"
            for kind, payload in run_debug_stream(req.problem, req.code, req.counterexample, dlang):
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
    pro = _require_pro(uid)              # 苏格拉底导师为 Pro 能力
    if pro:
        return pro
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
    pro = _require_pro(uid)              # 导师对话为 Pro 能力
    if pro:
        return pro
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
            if req.hints.strip():
                # 你（同一位导师）刚在「分层提示」里给过这些点拨，对话要与之连贯：
                # 学生很可能在追问你提示里抛出的问题，别表现得不知道自己说过什么、别重复发问。
                msgs.append(("system", "你刚刚以苏格拉底方式给这位学生的分层提示如下（按层递进）。"
                                       "学生现在的提问很可能正是顺着这些提示来的——请与它们保持连贯，"
                                       "顺势接着引导，不要重复你已经问过的问题，也不要表现得不知道自己提过它们：\n"
                                       + req.hints[:2500]))
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


# ------------------------- 导师审阅：行内批注 + 可选修订 -------------------------
@app.post("/api/review-code")
def review_code(req: ReviewCodeReq, request: Request, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if not req.code.strip():
        return JSONResponse({"error": "请先在编辑器里写代码"}, status_code=400)
    if len(req.code) > settings.MAX_CODE_CHARS:
        return JSONResponse({"error": "代码过长"}, status_code=400)
    blocked = _abuse_block(request, uid, "review")
    if blocked:
        return blocked
    try:
        result = agents.review_for_edit(req.problem, req.code, req.language)
        # 可信度护栏：AI 给了修订代码就先过一遍静态检查 + 沙箱实跑，
        # 附"已验证/未验证"标识，避免错误代码被当成正确答案直接交给学生。
        if result.get("has_fix") and result.get("proposed_code"):
            try:
                result["verification"] = verify.verify_code(
                    result["proposed_code"], req.language, req.problem_id or None)
            except Exception:
                result["verification"] = None
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ------------------------- 直接运行代码（自定义输入） -------------------------
@app.post("/api/run")
def run_code(req: RunReq, request: Request):
    # 代码执行是高危端点：即便游客也必须限流 + 限长，防止被当作免费算力 / 攻击跳板滥用
    ok, msg = guard.rate_limit_only(_ip(request))
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    if len(req.code) > settings.MAX_CODE_CHARS:
        return JSONResponse({"error": "代码过长"}, status_code=400)
    if len(req.stdin) > settings.MAX_CODE_CHARS:
        return JSONResponse({"error": "输入过长"}, status_code=400)
    lang = req.language if req.language in settings.SUPPORTED_LANGS else "python"
    return sandbox.run_code(req.code, lang, req.stdin)


# ------------------------- 学习进度仪表盘 -------------------------
@app.get("/api/stats")
def get_stats(arena_session: str = Cookie(default=None)):
    return progress.stats(_uid(arena_session))


# ------------------------- 个性化训练计划 -------------------------
@app.get("/api/study-plan")
def study_plan(request: Request, arena_session: str = Cookie(default=None)):
    """据画像挑题生成"今日训练计划"。确定性核心免费可用，仅按 IP 限流防刷。"""
    ok, msg = guard.rate_limit_only(_ip(request))
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    return studyplan.build_plan(_uid(arena_session))


# ------------------------- 代码可信度验证（静态检查 + 沙箱实跑） -------------------------
@app.post("/api/verify")
def verify_code(req: VerifyReq, request: Request):
    """对一段代码做静态检查 + 沙箱实跑，回传"已验证/未验证"可信标识。"""
    ok, msg = guard.rate_limit_only(_ip(request))
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    if len(req.code) > settings.MAX_CODE_CHARS:
        return JSONResponse({"error": "代码过长"}, status_code=400)
    lang = req.language if req.language in settings.SUPPORTED_LANGS else "python"
    return verify.verify_code(req.code, lang, req.problem_id or None)


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


# ------------------------- 社群讨论区 -------------------------
class PostReq(BaseModel):
    tag: str = "讨论"
    title: str = ""
    body: str = ""
    problem_id: str = ""      # 可选关联题目
    problem_title: str = ""


class ReplyReq(BaseModel):
    body: str = ""


@app.get("/api/community/posts")
def community_posts(tag: str = "", q: str = "", problem_id: str = "", sort: str = "hot"):
    return {"posts": community.list_posts(tag or None, q or None, problem_id or None,
                                          sort=sort if sort in ("hot", "new") else "hot")}


@app.get("/api/community/posts/{pid}")
def community_post(pid: int, arena_session: str = Cookie(default=None)):
    p = community.get_post(pid, _uid(arena_session))
    return p or JSONResponse({"error": "帖子不存在"}, status_code=404)


@app.post("/api/community/posts")
def community_create(req: PostReq, request: Request, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if uid is None:
        return JSONResponse({"error": "请先登录再发帖"}, status_code=401)
    if len(req.body) > settings.MAX_PROBLEM_CHARS:
        return JSONResponse({"error": "正文过长"}, status_code=400)
    blocked = _abuse_block(request, uid, "community")   # 审核含 LLM 调用，纳入限流配额
    if blocked:
        return blocked
    user = auth.get_user_by_id(uid)
    post, err = community.create_post(uid, user["username"] if user else "用户",
                                      req.tag, req.title, req.body,
                                      req.problem_id, req.problem_title)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    reward = _reward_community(request, uid, "post")
    return {"post": post, "reward": reward}


@app.post("/api/community/posts/{pid}/reply")
def community_reply(pid: int, req: ReplyReq, request: Request, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if uid is None:
        return JSONResponse({"error": "请先登录再回复"}, status_code=401)
    blocked = _abuse_block(request, uid, "community")
    if blocked:
        return blocked
    user = auth.get_user_by_id(uid)
    reply, err = community.add_reply(uid, user["username"] if user else "用户", pid, req.body)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    reward = _reward_community(request, uid, "reply")
    return {"reply": reply, "reward": reward}


@app.post("/api/community/posts/{pid}/like")
def community_like(pid: int, arena_session: str = Cookie(default=None)):
    uid = _uid(arena_session)
    if uid is None:
        return JSONResponse({"error": "请先登录再点赞"}, status_code=401)
    likes, liked = community.toggle_like(uid, pid)
    if likes is None:
        return JSONResponse({"error": "帖子不存在"}, status_code=404)
    return {"likes": likes, "liked": liked}


# ------------------------- 管理后台 -------------------------
ADMIN_COOKIE = "arena_admin"


class AdminLoginReq(BaseModel):
    username: str = ""
    password: str = ""


class AdminUserCreateReq(BaseModel):
    username: str
    password: str
    credits: int = 0


class AdminUserUpdateReq(BaseModel):
    username: str | None = None
    credits: int | None = None


class AdminResetPwReq(BaseModel):
    password: str


def _is_admin(token):
    return bool(token) and admin.check_token(token)


def _require_admin(token):
    """管理态守门：未通过返回 401 响应，通过返回 None。"""
    if not _is_admin(token):
        return JSONResponse({"error": "需要管理员登录"}, status_code=401)
    return None


@app.post("/api/admin/login")
def admin_login(req: AdminLoginReq, request: Request, resp: Response):
    ip = _ip(request)
    ok, msg = guard.rate_limit_only(ip)             # 全站限流
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    if admin.login_locked(ip):                       # 专属爆破锁定（更严格）
        return JSONResponse(
            {"error": "登录失败次数过多，管理员登录已临时锁定，请约 10 分钟后再试。"},
            status_code=429)
    if not admin.verify(req.username, req.password):
        admin.note_login_fail(ip)
        guard.log_event(None, ip, "admin_login_fail")   # 失败入审计，monitor.py 可见
        return JSONResponse({"error": "管理员账号或密码错误"}, status_code=401)
    admin.clear_login_fails(ip)
    guard.log_event(None, ip, "admin_login")            # 成功登录入审计
    resp.set_cookie(ADMIN_COOKIE, admin.make_token(), httponly=True, samesite="lax",
                    secure=settings.COOKIE_SECURE, max_age=12 * 3600)
    return {"ok": True}


@app.post("/api/admin/logout")
def admin_logout(resp: Response):
    resp.delete_cookie(ADMIN_COOKIE)
    return {"ok": True}


@app.get("/api/admin/session")
def admin_session(arena_admin: str = Cookie(default=None)):
    return {"admin": _is_admin(arena_admin)}


@app.get("/api/admin/overview")
def admin_overview(arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    return admin.overview()


@app.get("/api/admin/users")
def admin_users(q: str = "", page: int = 1, size: int = 20,
                arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    return admin.list_users(q, page, size)


@app.get("/api/admin/users/{uid}")
def admin_user_detail(uid: int, arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    d = admin.user_detail(uid)
    return d or JSONResponse({"error": "用户不存在"}, status_code=404)


@app.post("/api/admin/users")
def admin_user_create(req: AdminUserCreateReq, arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    user, err = admin.create_user(req.username, req.password, req.credits)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"user": user}


@app.patch("/api/admin/users/{uid}")
def admin_user_update(uid: int, req: AdminUserUpdateReq,
                      arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    user, err = admin.update_user(uid, req.username, req.credits)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"user": user}


@app.post("/api/admin/users/{uid}/reset-password")
def admin_user_reset_pw(uid: int, req: AdminResetPwReq,
                        arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    err = admin.reset_password(uid, req.password)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"ok": True}


@app.delete("/api/admin/users/{uid}")
def admin_user_delete(uid: int, arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    err = admin.delete_user(uid)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"ok": True}


@app.get("/api/admin/audit")
def admin_audit(limit: int = 80, arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    return {"audit": admin.recent_audit(limit)}


@app.get("/api/admin/posts")
def admin_posts(limit: int = 100, arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    return {"posts": admin.list_posts_admin(limit)}


@app.delete("/api/admin/posts/{pid}")
def admin_post_delete(pid: int, arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    err = admin.delete_post(pid)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"ok": True}


class AdminResolveReq(BaseModel):
    password: str


@app.get("/api/admin/reset-requests")
def admin_reset_list(status: str = "pending", arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    return {"requests": support.list_requests(status), "pending": support.pending_count()}


@app.post("/api/admin/reset-requests/{rid}/resolve")
def admin_reset_resolve(rid: int, req: AdminResolveReq,
                        arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    err = support.resolve_request(rid, req.password)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"ok": True}


@app.post("/api/admin/reset-requests/{rid}/dismiss")
def admin_reset_dismiss(rid: int, arena_admin: str = Cookie(default=None)):
    block = _require_admin(arena_admin)
    if block:
        return block
    err = support.dismiss_request(rid)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"ok": True}


# ------------------------- 前端静态资源 -------------------------
@app.get("/")
def index():
    return FileResponse(settings.STATIC_DIR + "/index.html")


@app.get("/admin")
def admin_page():
    return FileResponse(settings.STATIC_DIR + "/admin.html")


app.mount("/", StaticFiles(directory=settings.STATIC_DIR), name="static")
