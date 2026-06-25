# -*- coding: utf-8 -*-
"""校验 i18n.js 中英 key 是否齐全。"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = io.open(os.path.join(ROOT, "static", "i18n.js"), encoding="utf-8").read()


def keys(block):
    return set(re.findall(r'"([\w.]+)"\s*:', block))


zh_start = src.index("zh: {")
en_start = src.index("en: {")
zh = keys(src[zh_start:en_start])
en = keys(src[en_start:])
miss_en = sorted(zh - en)
miss_zh = sorted(en - zh)
print("zh keys:", len(zh), "| en keys:", len(en))
print("missing in en:", miss_en)
print("missing in zh:", miss_zh)
for k in ["plan.title", "plan.refresh", "plan.loading", "dash.growth", "dash.growth.sub"]:
    print("  ", k, "zh=" + ("Y" if k in zh else "N"), "en=" + ("Y" if k in en else "N"))
assert not miss_en and not miss_zh, "i18n 双语不齐"
print("i18n parity OK")
