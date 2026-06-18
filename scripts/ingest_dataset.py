# -*- coding: utf-8 -*-
"""从公开竞赛数据集导入真题（题面 + 标签 + 难度 + 真实测试数据）。

数据源：DeepMind CodeContests（Codeforces / AtCoder 等真实竞赛题，带官方测试数据）。
走 HuggingFace 国内镜像 hf-mirror.com，流式拉取，不下整包。

产出：
  - data/problems.json   追加导入的题（题面/标签/难度/样例），供 RAG 与题库下拉使用
  - data/tests/<id>.json  每题的真实测试数据（input / expected / kind），判题真值来源

用法：
  python scripts/ingest_dataset.py            # 默认导入约 120 道
  python scripts/ingest_dataset.py 5          # 只导入 5 道（先验证管线）
  python scripts/ingest_dataset.py 120 3000   # 120 道，最多扫描 3000 条候选
"""
import json
import os
import sys

# 必须在 import datasets 之前设置镜像
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
TESTS_DIR = os.path.join(DATA_DIR, "tests")
PROBLEMS_JSON = os.path.join(DATA_DIR, "problems.json")

# 单条用例输入/输出超过此长度则跳过（控制判题耗时与文件体积）
MAX_IO_CHARS = 3000
# 每题最多保留的测试用例数
MAX_CASES = 12
# 题面长度范围（过短无意义，过长不适合教学展示）
MIN_DESC, MAX_DESC = 200, 6000
# 难度分范围（Codeforces rating，取相对易上手的区间）
MIN_RATING, MAX_RATING = 800, 1600

# cf_tags 主标签 → 中文题型
TAG2TYPE = [
    ("dp", "动态规划"),
    ("greedy", "贪心"),
    ("graphs", "图论"),
    ("dfs and similar", "图论"),
    ("trees", "图论"),
    ("shortest paths", "图论"),
    ("strings", "字符串"),
    ("data structures", "数据结构"),
    ("binary search", "二分查找"),
    ("two pointers", "双指针"),
    ("sortings", "排序"),
    ("number theory", "数学"),
    ("math", "数学"),
    ("combinatorics", "数学"),
    ("brute force", "枚举"),
    ("constructive algorithms", "构造"),
    ("implementation", "模拟"),
]


def pick_type(tags):
    tagset = set(t.lower() for t in tags)
    for key, zh in TAG2TYPE:
        if key in tagset:
            return zh
    return "综合"


def rating_to_difficulty(rating):
    if rating <= 1000:
        return "简单"
    if rating <= 1400:
        return "中等"
    return "困难"


def clean_title(name):
    # CodeContests 的 name 形如 "1549_E. Mr. Kitayuta..."，去掉前缀编号
    t = name.strip()
    if ". " in t:
        t = t.split(". ", 1)[1]
    return t[:80]


def extract_cases(example):
    """从 public / generated 测试中抽取干净的 stdin/stdout 用例。"""
    cases = []

    def add(group, kind):
        ins = (group or {}).get("input", []) or []
        outs = (group or {}).get("output", []) or []
        for i in range(min(len(ins), len(outs))):
            inp, out = ins[i], outs[i]
            if inp is None or out is None:
                continue
            if len(inp) > MAX_IO_CHARS or len(out) > MAX_IO_CHARS:
                continue
            cases.append({"input": inp, "expected": out, "kind": kind})

    add(example.get("public_tests"), "sample")     # 题面样例：最可信
    if len(cases) < MAX_CASES:
        add(example.get("generated_tests"), "system")  # 官方生成数据
    if len(cases) < MAX_CASES:
        add(example.get("private_tests"), "system")
    # 去重 + 截断
    seen, uniq = set(), []
    for c in cases:
        key = c["input"]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
        if len(uniq) >= MAX_CASES:
            break
    return uniq


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    max_scan = int(sys.argv[2]) if len(sys.argv) > 2 else max(2000, target * 25)

    print("[*] HF_ENDPOINT =", os.environ["HF_ENDPOINT"])
    print("[*] 流式加载 deepmind/code_contests (train) ...")
    from datasets import load_dataset
    ds = load_dataset("deepmind/code_contests", split="train",
                      streaming=True, trust_remote_code=True)

    os.makedirs(TESTS_DIR, exist_ok=True)
    with open(PROBLEMS_JSON, "r", encoding="utf-8") as f:
        problems = json.load(f)
    # 保留原有非 CC 题（手工题库），CC* 全部重建
    problems = [p for p in problems if not str(p.get("id", "")).startswith("CC")]

    new_problems = []
    scanned = 0
    for example in ds:
        scanned += 1
        if scanned > max_scan:
            break
        if len(new_problems) >= target:
            break

        rating = example.get("cf_rating") or 0
        if not (MIN_RATING <= rating <= MAX_RATING):
            continue
        desc = (example.get("description") or "").strip()
        if not (MIN_DESC <= len(desc) <= MAX_DESC):
            continue
        cases = extract_cases(example)
        if len(cases) < 2:        # 至少要有可判的用例
            continue

        idx = len(new_problems) + 1
        pid = "CC%04d" % idx
        tags = example.get("cf_tags") or []
        samples = [c for c in cases if c["kind"] == "sample"]
        sample = samples[0] if samples else cases[0]

        new_problems.append({
            "id": pid,
            "title": clean_title(example.get("name", pid)),
            "type": pick_type(tags),
            "tags": tags[:6],
            "difficulty": rating_to_difficulty(rating),
            "difficulty_score": rating,
            "description": desc,
            "sample_input": sample["input"],
            "sample_output": sample["expected"],
            "source": "Codeforces",
            "has_real_tests": True,
        })
        with open(os.path.join(TESTS_DIR, pid + ".json"), "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False)

        if len(new_problems) % 10 == 0:
            print("    已导入 %d 道（扫描 %d 条）" % (len(new_problems), scanned))

    problems.extend(new_problems)
    with open(PROBLEMS_JSON, "w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)

    print("[+] 完成：新增 %d 道真题，题库共 %d 道（扫描 %d 条候选）"
          % (len(new_problems), len(problems), scanned))
    print("[+] 测试数据目录：", TESTS_DIR)


if __name__ == "__main__":
    main()
