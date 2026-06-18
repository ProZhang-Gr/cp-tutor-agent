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


class Settings:
    # DeepSeek（OpenAI 兼容协议）
    DEEPSEEK_API_KEY = _load_api_key()
    BASE_URL = "https://api.deepseek.com"

    # 登录态签名密钥（生产环境用环境变量覆盖）
    SECRET_KEY = os.getenv("SECRET_KEY", "arena-dev-secret-change-in-prod")
    # 数据库：设了 DATABASE_URL（Postgres）则持久化，否则用本地 SQLite
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

    # deepseek-chat = V3 通用模型；deepseek-reasoner = R1 深度推理模型
    MODEL_CHAT = "deepseek-chat"
    MODEL_REASONER = "deepseek-reasoner"

    # 路径
    ROOT = _ROOT
    DATA_DIR = os.path.join(_ROOT, "data")
    STATIC_DIR = os.path.join(_ROOT, "static")
    PROBLEM_BANK = os.path.join(DATA_DIR, "problems.json")
    DB_PATH = os.path.join(DATA_DIR, "progress.db")

    # 沙箱
    SANDBOX_TIMEOUT = 6  # 单个测试用例超时（秒）


settings = Settings()
