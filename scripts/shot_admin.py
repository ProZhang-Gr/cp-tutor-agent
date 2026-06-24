# -*- coding: utf-8 -*-
"""管理后台真实浏览器验收：登录 -> 概览/用户/密码申请/活动 截图，并捕获 JS 报错。

跑：DEMO_BASE=http://127.0.0.1:8023 D:/Anaconda3/python.exe scripts/shot_admin.py
"""
import os
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DEMO_BASE", "http://127.0.0.1:8023").rstrip("/")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_shots")
os.makedirs(OUT, exist_ok=True)
errors = []


def shot(page, name):
    p = os.path.join(OUT, "admin_%s.png" % name)
    page.screenshot(path=p, full_page=False)
    print("  📸", os.path.basename(p))


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1480, "height": 940}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE + "/admin", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("#gate", timeout=8000)
        shot(page, "01_gate")

        page.fill("#gate-user", "manager")
        page.fill("#gate-pass", "123456")
        page.click("#gate-btn")
        page.wait_for_selector("#shell:not(.hidden)", timeout=8000)
        page.wait_for_timeout(1200)
        shot(page, "02_overview")

        page.click('.nav-item[data-view="users"]'); page.wait_for_timeout(900)
        shot(page, "03_users")

        page.click('.nav-item[data-view="resets"]'); page.wait_for_timeout(800)
        shot(page, "04_resets")

        page.click('.nav-item[data-view="activity"]'); page.wait_for_timeout(800)
        shot(page, "05_activity")

        page.click('.nav-item[data-view="content"]'); page.wait_for_timeout(800)
        shot(page, "06_content")

        # 打开「新增用户」弹窗看一眼
        page.click('.nav-item[data-view="users"]'); page.wait_for_timeout(600)
        page.click("#add-user-btn"); page.wait_for_timeout(500)
        shot(page, "07_modal")

        ctx.close(); b.close()

    print("\nJS 报错：", "无" if not errors else "")
    for e in errors:
        print("  !!", e)
    print("完成，截图在", OUT)


if __name__ == "__main__":
    main()
