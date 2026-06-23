# -*- coding: utf-8 -*-
"""代码执行沙箱。

在独立子进程中运行学生代码，喂入标准输入、捕获标准输出，带超时控制；
再把实际输出与期望输出逐一比对，给出判题结果（AC/WA/TLE/RE/CE）。

注意：这是教学用的轻量沙箱，依赖子进程隔离 + 超时 + 临时工作目录，
并未做系统调用级别的硬隔离。生产环境应换用容器/seccomp。
"""
import os
import subprocess
import sys
import tempfile

from config import settings

# 子进程仅继承这些环境变量；密钥（如 DEEPSEEK_API_KEY）一律不传入，
# 防止公网部署时访客通过提交代码读取 os.environ 窃取密钥。
_SAFE_ENV_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME",
                  "LANG", "LC_ALL", "LC_CTYPE")


def _safe_env():
    env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# 判题状态
AC = "AC"   # Accepted 通过
WA = "WA"   # Wrong Answer 答案错误
TLE = "TLE"  # Time Limit Exceeded 超时
RE = "RE"   # Runtime Error 运行错误
CE = "CE"   # Compile Error 编译/语法错误


def _normalize(s):
    """忽略行尾空白和末尾空行的输出归一化，贴近 OJ 判题习惯。"""
    lines = [ln.rstrip() for ln in s.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _clean_trace(text, *paths):
    """去掉报错里暴露的沙箱真实路径，统一显示为 main.py，避免泄露目录结构。"""
    if not text:
        return text
    out = text
    for p in paths:
        if p:
            out = out.replace(p, "main.py")
    return out


def run_python(code, stdin_data="", timeout=None):
    """运行一段 Python 代码，返回执行详情字典。

    目录布局刻意做了信息收敛：代码文件放在隐藏的 .src 子目录，运行时把 cwd
    指向同级的空 work 目录——这样学生代码里 os.getcwd()/os.listdir() 看到的
    是一个干净空目录，不暴露脚本名与沙箱命名前缀。报错里的真实路径也会被清洗。
    （注：这是教学级隔离，非系统级硬隔离；硬隔离仍需容器/seccomp。）
    """
    timeout = timeout or settings.SANDBOX_TIMEOUT
    base = tempfile.mkdtemp(prefix="run_")
    src_dir = os.path.join(base, ".src")
    work_dir = os.path.join(base, "work")
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    src = os.path.join(src_dir, "main.py")
    with open(src, "w", encoding="utf-8") as f:
        f.write(code)

    # 先做一次语法编译检查，区分 CE 与 RE（只回报行号，不带路径）
    try:
        compile(code, src, "exec")
    except SyntaxError as e:
        return {"status": CE, "stdout": "", "stderr": "语法错误: %s (第 %s 行)" % (e.msg, e.lineno),
                "time_ms": 0}

    try:
        proc = subprocess.run(
            [sys.executable, src],
            input=stdin_data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=work_dir,
            env=_safe_env(),
        )
    except subprocess.TimeoutExpired:
        return {"status": TLE, "stdout": "", "stderr": "超过时间限制 %ss" % timeout,
                "time_ms": int(timeout * 1000)}
    except Exception as e:
        return {"status": RE, "stdout": "", "stderr": str(e), "time_ms": 0}

    if proc.returncode != 0:
        return {"status": RE, "stdout": proc.stdout or "",
                "stderr": _clean_trace((proc.stderr or "").strip(), src, src_dir, base)[-1500:],
                "time_ms": 0}
    return {"status": "OK", "stdout": proc.stdout or "", "stderr": proc.stderr or "",
            "time_ms": 0}


def judge(code, test_cases, timeout=None):
    """对一组测试用例判题，返回每个用例的结果与汇总。"""
    results = []
    passed = 0
    for i, tc in enumerate(test_cases):
        stdin_data = tc.get("input", "") or ""
        expected = tc.get("expected", "") or ""
        run = run_python(code, stdin_data, timeout)

        if run["status"] in (CE, TLE, RE):
            status = run["status"]
        elif expected.strip() == "":
            # 没有可信期望输出，只验证能正常运行
            status = "RUN"
        elif _normalize(run["stdout"]) == _normalize(expected):
            status = AC
        else:
            status = WA

        if status in (AC, "RUN"):
            passed += 1

        results.append({
            "index": i,
            "name": tc.get("name", "用例 %d" % (i + 1)),
            "category": tc.get("category", ""),
            "status": status,
            "input": stdin_data,
            "expected": expected,
            "actual": run["stdout"],
            "stderr": run["stderr"],
            "note": tc.get("note", ""),
        })

    total = len(test_cases)
    all_ac = total > 0 and passed == total and all(
        r["status"] == AC for r in results if r["expected"].strip()
    )
    return {
        "results": results,
        "passed": passed,
        "total": total,
        "all_passed": passed == total and total > 0,
        "verdict": AC if all_ac else (results[0]["status"] if total == 1 else "部分通过"),
    }
