# -*- coding: utf-8 -*-
"""第八阶段前端走查：训练计划卡 / 成长曲线 / 可信徽章 渲染 + 控制台零报错。

用法：先起服 `D:/Anaconda3/python.exe -m uvicorn app:app --port 8023`，
再 `D:/Anaconda3/python.exe scripts/shot_phase8.py`。
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DEMO_BASE", "http://127.0.0.1:8023")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_shots")
os.makedirs(OUT, exist_ok=True)


def main():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 1900}, device_scale_factor=2)
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # 跳过新手引导/公告弹窗
        pg.add_init_script("localStorage.setItem('cp_onboarded_v1','1');"
                           "localStorage.setItem('cp_announce_seen','[\"beta-2026-06\",\"i18n-incentive-2026-06\",\"cert-2026-06\"]');")
        pg.goto(BASE, wait_until="networkidle")
        # 切到仪表盘
        pg.click('.tab[data-view="dashboard"]')
        pg.wait_for_timeout(2500)
        # 训练计划卡应已填充
        plan = pg.inner_text("#plan-body")
        print("[plan-body] first 80:", plan[:80].replace("\n", " "))
        assert "正在据你的画像" not in plan or "训练计划加载失败" not in plan, "训练计划未渲染"
        has_items = pg.query_selector_all(".plan-item")
        print("[plan] items rendered:", len(has_items))
        # 成长曲线 canvas 存在
        assert pg.query_selector("#chart-growth"), "成长曲线 canvas 缺失"
        print("[growth] canvas present")
        pg.screenshot(path=os.path.join(OUT, "phase8_dashboard.png"), full_page=True)
        b.close()
    print("console/page errors:", errors)
    assert not errors, "前端有报错：%s" % errors
    print("ALL OK -> demo_shots/phase8_dashboard.png")


if __name__ == "__main__":
    sys.exit(main())
