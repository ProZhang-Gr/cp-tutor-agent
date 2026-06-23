# -*- coding: utf-8 -*-
"""全局配置：API、模型、路径。"""
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_api_key():
    """密钥来源优先级：环境变量 > 本地密钥文件 .deepseek_key > 空。

    - 云端部署：在平台 Secret/环境变量里设 DEEPSEEK_API_KEY（绝不写进仓库）。
    - 本地运行：把 key 放进同目录 .deepseek_key 文件（已被 .gitignore 忽略）。
    """
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    key_file = os.path.join(_ROOT, ".deepseek_key")
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _load_secret_key():
    """登录态签名密钥：优先环境变量；未设置则生成临时随机密钥并告警。

    不再使用硬编码默认值——否则任何忘记设环境变量的部署都共享同一密钥，
    攻击者可据此伪造任意用户的会话。临时密钥在进程重启后失效（登录态作废），
    生产环境务必通过环境变量固定 SECRET_KEY。
    """
    key = os.getenv("SECRET_KEY", "").strip()
    if key:
        return key
    import secrets
    print("[config] 警告：未设置 SECRET_KEY 环境变量，已生成临时随机密钥；"
          "进程重启后登录态会失效。生产环境请在环境变量里固定 SECRET_KEY。")
    return secrets.token_hex(32)


class Settings:
    # DeepSeek（OpenAI 兼容协议）
    DEEPSEEK_API_KEY = _load_api_key()
    BASE_URL = "https://api.deepseek.com"

    # 登录态签名密钥（生产环境用环境变量覆盖；缺省随机生成）
    SECRET_KEY = _load_secret_key()
    # 数据库：设了 DATABASE_URL（Postgres）则持久化，否则用本地 SQLite
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    # 仅在 HTTPS 下下发 Secure Cookie：Render 自动注入 RENDER 变量；本地 http 保持 False 以免登录失效
    COOKIE_SECURE = (os.getenv("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")
                     or bool(os.getenv("RENDER")))
    # LLM 调用稳健性
    LLM_MAX_RETRIES = 2        # 网络抖动时自动重试次数
    LLM_TIMEOUT = 120          # 单次请求超时（秒）

    # deepseek-chat = V3 通用模型；deepseek-reasoner = R1 深度推理模型
    MODEL_CHAT = "deepseek-chat"
    MODEL_REASONER = "deepseek-reasoner"

    # 路径
    ROOT = _ROOT
    DATA_DIR = os.path.join(_ROOT, "data")
    STATIC_DIR = os.path.join(_ROOT, "static")
    PROBLEM_BANK = os.path.join(DATA_DIR, "problems.json")
    TESTS_DIR = os.path.join(DATA_DIR, "tests")  # 真题的真实测试数据（判题真值）
    DB_PATH = os.path.join(DATA_DIR, "progress.db")

    # 沙箱
    SANDBOX_TIMEOUT = 6  # 单个测试用例超时（秒）

    # 对拍（差分测试）：无真实数据时，用暴力解 + 随机生成器 stress test
    STRESS_TRIALS = 30     # 随机对拍轮数
    STRESS_TIMEOUT = 4     # 对拍时单次运行超时（秒），比正式判题略短

    # Agentic 调试回路（ReAct）
    DEBUG_MAX_STEPS = 4    # 调试 agent 最多迭代轮数（每轮可调一次沙箱）

    # 防滥用
    RATE_PER_MIN = 20          # 每 IP 每分钟请求上限
    QUOTA_GUEST = 30           # 游客每日 LLM 调用上限
    QUOTA_USER = 100           # 登录(普通)用户每日上限；Pro 在 Phase3 放开
    # 全站每日 LLM 调用总上限（含 Pro）：给 DeepSeek 花费兜底，防被刷爆账单。
    # 达到上限后所有人当日 AI 功能降级提示。可用环境变量覆盖。
    GLOBAL_DAILY_LLM_CAP = int(os.getenv("GLOBAL_DAILY_LLM_CAP", "3000") or "0")
    MAX_PROBLEM_CHARS = 8000   # 题面长度上限
    MAX_CODE_CHARS = 20000     # 代码长度上限
    MAX_QUESTION_CHARS = 2000  # 提问长度上限

    # 功能权限分级：以下高级能力需 Pro 算力点（普通分析 / 导师审阅免费）
    PRO_ONLY = ("hint", "chat")   # 苏格拉底导师、导师对话；深度分析另在 analyze 内判定
    # 激励广告（模拟）：看广告得算力点
    AD_REWARD_POINTS = 5       # 每看完一次广告发放的算力点
    AD_DAILY_LIMIT = 5         # 每用户每日看广告得点次数上限


settings = Settings()
