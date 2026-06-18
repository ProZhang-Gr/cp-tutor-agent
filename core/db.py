# -*- coding: utf-8 -*-
"""数据库抽象层：默认 SQLite，设了 DATABASE_URL(Postgres) 则切换为持久化。

统一用 ? 占位符写 SQL，Postgres 下自动转成 %s。
连接按调用即开即关，低并发的教学/演示场景足够稳。
"""
import os
import sqlite3

from config import settings

DATABASE_URL = settings.DATABASE_URL
IS_PG = DATABASE_URL.startswith("postgres")

if IS_PG:
    import psycopg2
    import psycopg2.extras


def _conn():
    if IS_PG:
        return psycopg2.connect(DATABASE_URL)
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    c = sqlite3.connect(settings.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _adapt(sql):
    return sql.replace("?", "%s") if IS_PG else sql


def execute(sql, params=()):
    """执行写操作，返回新插入行的 id（若适用）。"""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(_adapt(sql), params)
    new_id = None
    try:
        if IS_PG and "RETURNING" in sql.upper():
            new_id = cur.fetchone()[0]
        elif not IS_PG:
            new_id = cur.lastrowid
    except Exception:
        new_id = None
    conn.commit()
    cur.close()
    conn.close()
    return new_id


def query(sql, params=()):
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if IS_PG else conn.cursor()
    cur.execute(_adapt(sql), params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def init_schema():
    idtype = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if IS_PG else "REAL"
    execute("""CREATE TABLE IF NOT EXISTS users (
        id %s,
        username TEXT UNIQUE NOT NULL,
        pw_hash  TEXT NOT NULL,
        salt     TEXT NOT NULL,
        created_at %s
    )""" % (idtype, real))
    execute("""CREATE TABLE IF NOT EXISTS submissions (
        id %s,
        user_id INTEGER,
        ts %s,
        problem_title TEXT,
        problem_type  TEXT,
        difficulty    TEXT,
        passed       INTEGER,
        tests_passed INTEGER,
        tests_total  INTEGER,
        score        INTEGER,
        error_kind   TEXT
    )""" % (idtype, real))
