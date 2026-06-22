# -*- coding: utf-8 -*-
"""社群讨论区：帖子 / 回帖 / 点赞 + 内容审核护栏。

设计取舍（见 DESIGN.md §7）：UGC 在国内有内容安全责任，因此发帖/回帖
都先过审核护栏。护栏分两层：
  1) 确定性关键词 + 长度过滤（始终生效，不依赖网络，是真正的兜底保证）；
  2) LLM 审核 agent（语义层，best-effort；不可用时放行，保证可用性）。
"""
import time

from sqlalchemy import select

from core.db import session_scope
from core.models import Post, PostLike, Reply

# 合法标签白名单（与前端筛选一致）
TAGS = ["求助", "题解", "讨论", "反馈"]
TITLE_MAX = 80
BODY_MAX = 4000
BODY_MIN = 2

# 关键词黑名单：明显辱骂 / 垃圾广告 / 引流。演示用的精简表，确定性兜底。
_BANNED = [
    "fuck", "shit", "傻逼", "煞笔", "操你", "草你", "尼玛", "妈的", "贱货",
    "加微信", "加qq", "vx私聊", "代写包过", "刷单", "兼职日结", "博彩", "赌博",
    "色情", "av资源", "开票", "代开发票", "办证",
]


def _keyword_check(text):
    low = (text or "").lower()
    for w in _BANNED:
        if w and w.lower() in low:
            return False, "包含疑似辱骂 / 广告引流等不当内容，已被审核拦截"
    return True, ""


def _llm_moderate(text):
    """语义审核（best-effort）。失败一律放行——关键词层已兜住最坏情况。"""
    try:
        from core.llm import get_llm
        llm = get_llm(temperature=0, max_tokens=24)
        out = llm.invoke([
            ("system", "你是社区内容安全审核员。判断下面这段帖子是否包含违法、人身辱骂、"
                       "色情、政治敏感或垃圾广告引流。只回复一行：合规 OK 就回 OK；"
                       "不合规就回 BLOCK:简短原因。除此之外不要输出任何内容。"),
            ("user", (text or "")[:1000]),
        ])
        ans = (getattr(out, "content", "") or "").strip()
        if ans.upper().startswith("BLOCK"):
            reason = ans.split(":", 1)[1].strip() if ":" in ans else ans.split("：", 1)[-1].strip()
            return False, "AI 审核未通过：" + (reason or "内容不合规")
        return True, ""
    except Exception:
        return True, ""


def moderate(text):
    """对外的审核入口：先确定性关键词，再 LLM 语义。返回 (ok, reason)。"""
    ok, reason = _keyword_check(text)
    if not ok:
        return False, reason
    return _llm_moderate(text)


def _snippet(body, n=120):
    s = (body or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _post_brief(p):
    return {
        "id": p.id, "username": p.username, "tag": p.tag, "title": p.title,
        "snippet": _snippet(p.body), "likes": p.likes, "reply_count": p.reply_count,
        "created_at": p.created_at,
    }


def list_posts(tag=None, limit=60):
    with session_scope() as s:
        q = select(Post)
        if tag:
            q = q.where(Post.tag == tag)
        q = q.order_by(Post.created_at.desc()).limit(limit)
        return [_post_brief(p) for p in s.scalars(q)]


def get_post(post_id, user_id=None):
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return None
        replies = list(s.scalars(
            select(Reply).where(Reply.post_id == post_id).order_by(Reply.created_at.asc())))
        liked = False
        if user_id is not None:
            liked = s.scalar(select(PostLike).where(
                PostLike.post_id == post_id, PostLike.user_id == user_id)) is not None
        return {
            "id": p.id, "username": p.username, "tag": p.tag, "title": p.title,
            "body": p.body, "likes": p.likes, "reply_count": p.reply_count,
            "created_at": p.created_at, "liked": liked,
            "replies": [{
                "id": r.id, "username": r.username, "body": r.body, "created_at": r.created_at,
            } for r in replies],
        }


def create_post(user_id, username, tag, title, body):
    title = (title or "").strip()
    body = (body or "").strip()
    if tag not in TAGS:
        return None, "请选择正确的板块标签"
    if not title:
        return None, "标题不能为空"
    if len(title) > TITLE_MAX:
        return None, "标题过长（上限 %d 字）" % TITLE_MAX
    if len(body) < BODY_MIN:
        return None, "正文太短，多写两句吧"
    if len(body) > BODY_MAX:
        return None, "正文过长（上限 %d 字）" % BODY_MAX
    ok, reason = moderate(title + "\n" + body)
    if not ok:
        return None, reason
    with session_scope() as s:
        p = Post(user_id=user_id, username=username, tag=tag, title=title,
                 body=body, likes=0, reply_count=0, created_at=time.time())
        s.add(p)
        s.flush()
        return _post_brief(p), None


def add_reply(user_id, username, post_id, body):
    body = (body or "").strip()
    if len(body) < BODY_MIN:
        return None, "回复太短了"
    if len(body) > BODY_MAX:
        return None, "回复过长"
    ok, reason = moderate(body)
    if not ok:
        return None, reason
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return None, "帖子不存在或已删除"
        r = Reply(post_id=post_id, user_id=user_id, username=username,
                  body=body, created_at=time.time())
        s.add(r)
        p.reply_count = (p.reply_count or 0) + 1
        s.flush()
        return {"id": r.id, "username": r.username, "body": r.body,
                "created_at": r.created_at}, None


def toggle_like(user_id, post_id):
    """点赞 / 取消点赞。返回 (likes, liked)。"""
    with session_scope() as s:
        p = s.get(Post, post_id)
        if not p:
            return None, None
        existing = s.scalar(select(PostLike).where(
            PostLike.post_id == post_id, PostLike.user_id == user_id))
        if existing:
            s.delete(existing)
            p.likes = max(0, (p.likes or 0) - 1)
            liked = False
        else:
            s.add(PostLike(post_id=post_id, user_id=user_id, created_at=time.time()))
            p.likes = (p.likes or 0) + 1
            liked = True
        s.flush()
        return p.likes, liked


_SEED = [
    ("题解", "二分查找为什么是 lo<=hi 而不是 lo<hi？",
     "刷题时老在边界条件翻车。整理了一下：闭区间 [lo, hi] 写法用 lo<=hi，"
     "因为 lo==hi 时区间里还有一个元素要判；mid 命中就返回，否则 lo=mid+1 或 hi=mid-1。"
     "开区间写法才是 lo<hi。建议一套写法用到底，不要混。"),
    ("求助", "Dijkstra 能处理负权边吗？被面试官问懵了",
     "今天面试被问 Dijkstra 遇到负权边会怎样，我当时只记得『不能用』，"
     "但说不清为什么。求大佬解释下，以及负权该换什么算法？"),
    ("讨论", "动态规划怎么找状态转移方程？有没有套路",
     "感觉 DP 最难的不是写代码，是定义 dp[i] 是什么、想清楚从哪个子问题转移过来。"
     "大家有没有自己的一套思考流程？比如先想『最后一步』之类的。"),
    ("反馈", "建议给『算法图解』再加一个并查集的动画",
     "刚体验了算法图解板块，BFS 那个动图很直观！希望能加上并查集（路径压缩 / 按秩合并）"
     "和线段树的可视化，这两个光看代码很难想象。"),
]


def seed_if_empty():
    """首次启动且空表时灌入几条引导帖，让社群一打开就不冷清。"""
    try:
        with session_scope() as s:
            if s.scalar(select(Post.id).limit(1)) is not None:
                return
            now = time.time()
            for i, (tag, title, body) in enumerate(_SEED):
                s.add(Post(user_id=None, username="ARENA 小助手", tag=tag, title=title,
                           body=body, likes=2 + i, reply_count=0, created_at=now - (i + 1) * 3600))
    except Exception as e:
        print("[community] seed 跳过：%s" % e)
