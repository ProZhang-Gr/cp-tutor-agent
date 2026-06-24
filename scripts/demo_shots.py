# -*- coding: utf-8 -*-
"""PPT 演示截图：用 Playwright 驱动一个干净的浏览器，按流程自动走查线上站点，
把第四阶段新增的 5 个功能逐屏拍成高清 PNG。

- 目标：默认线上 https://cp-tutor-agent.onrender.com（已部署新版）。
- 轻量播种：注册演示号 → 充值成 Pro → 签到 → 灌学习行为埋点 → 发两条社群帖，
  让顶栏 / 社群 / 学习投入卡片「有数据、不冷清」。全部走 HTTP API，瞬时、无需 LLM。
- 截图：工作台 / 仪表盘 / 社群 / 算法图解 的中英两版 + 几个弹窗。device_scale_factor=2
  出 2 倍图，往 PPT 里拖即清晰。
- 注：仪表盘的图表/薄弱题型/结业证书需要真实做题数据才会「满」，本脚本不刷题
  （那要花 LLM 调用）；如需，另说。

运行：D:/Anaconda3/python.exe scripts/demo_shots.py
依赖：playwright（pip install playwright && python -m playwright install chromium）
"""
import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DEMO_BASE", "https://cp-tutor-agent.onrender.com").rstrip("/")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_shots")
os.makedirs(OUT, exist_ok=True)

U = "demo_%d" % (int(time.time()) % 100000)
PW = "demo12345"

SAMPLE_PROBLEM = (
    "【题目】两数之和\n"
    "给定一个整数数组 nums 和一个目标值 target，请在数组中找出和为 target 的两个数，返回其下标。\n"
    "【输入格式】第一行两个整数 n 与 target；第二行 n 个整数。\n"
    "【输出格式】两个下标，空格分隔（0 起）。\n"
    "样例输入：\n4 9\n2 7 11 15\n样例输出：\n0 1\n"
)

_n = 0
def shot(page, name, full=True):
    global _n
    _n += 1
    path = os.path.join(OUT, "%02d_%s.png" % (_n, name))
    page.screenshot(path=path, full_page=full)
    print("  📸 %s" % os.path.basename(path))

def jpost(req, path, obj):
    """显式发 JSON，避免 dict 被当表单编码导致 FastAPI 422。"""
    return req.post(BASE + path, data=json.dumps(obj),
                    headers={"Content-Type": "application/json"})

def click_tab(page, view):
    page.click('.tab[data-view="%s"]' % view)
    page.wait_for_timeout(900)

def toggle_lang(page):
    page.click("#lang-toggle")
    page.wait_for_timeout(700)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
        req = ctx.request

        print("== 播种演示数据（HTTP API，瞬时）==")
        r = jpost(req, "/api/register", {"username": U, "password": PW})
        print("  注册:", r.status)
        print("  充值:", jpost(req, "/api/recharge", {"yuan": 30}).status)   # → Pro + 300 算力点
        print("  签到:", jpost(req, "/api/checkin", {}).status)              # 当日已签到
        # 学习行为埋点：今天 + 历史两段，让「学习投入」卡片有数
        jpost(req, "/api/telemetry", {"problem_id": "P1", "active_seconds": 1500, "keystrokes": 820, "runs": 6, "submits": 3})
        jpost(req, "/api/telemetry", {"problem_id": "P2", "active_seconds": 1100, "keystrokes": 540, "runs": 4, "submits": 2})
        # 社群两帖（含审核护栏，best-effort）
        print("  发帖1:", jpost(req, "/api/community/posts", {"tag": "题解", "title": "单调栈 O(n) 解接雨水",
                 "body": "维护一个高度递减的单调栈，遇到更高的柱子就出栈结算每一层能接的水，整体 O(n)。"}).status)
        jpost(req, "/api/community/posts", {"tag": "求助", "title": "二分边界总差一怎么办",
                 "body": "闭区间 [lo,hi] 用 lo<=hi，命中即返回，否则收缩区间；建议一套写法用到底不要混。"})

        page = ctx.new_page()
        print("== 打开站点（冷启动可能稍慢）==")
        page.goto(BASE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1500)
        # 工作台贴一道样例题，避免空荡
        try:
            page.fill("#problem-input", SAMPLE_PROBLEM)
        except Exception as e:
            print("  (填题跳过:", e, ")")
        page.wait_for_timeout(400)

        print("== 截图：工作台 中/英 ==")
        shot(page, "workspace_zh")
        toggle_lang(page)
        shot(page, "workspace_en")          # 头牌：整页切英文

        print("== 截图：仪表盘 英/中（画像/学习投入/成就）==")
        click_tab(page, "dashboard")
        page.wait_for_timeout(1200)
        shot(page, "dashboard_en")
        # 局部特写
        for sel, nm in [("#profile-card", "profile_card_en"),
                        ("#engage-card", "engage_card_en"),
                        ("#ach-card", "ach_card_en")]:
            try:
                page.locator(sel).screenshot(path=os.path.join(OUT, "el_%s.png" % nm))
                print("  📸 el_%s.png" % nm)
            except Exception as e:
                print("  (特写跳过 %s: %s)" % (nm, e))
        toggle_lang(page)                    # 切回中文
        page.wait_for_timeout(800)
        shot(page, "dashboard_zh")

        print("== 截图：社群 中/英 ==")
        click_tab(page, "community")
        page.wait_for_timeout(1200)
        shot(page, "community_zh")
        toggle_lang(page)
        page.wait_for_timeout(900)
        shot(page, "community_en")
        toggle_lang(page)                    # 回中文

        print("== 截图：算法图解 ==")
        click_tab(page, "visualizer")
        page.wait_for_timeout(800)
        try:
            page.locator("#vz-list .vz-item, #vz-list button, #vz-list >*").first.click()
            page.wait_for_timeout(900)
            page.click("#vz-next")
            page.wait_for_timeout(500)
            page.click("#vz-next")
            page.wait_for_timeout(500)
        except Exception as e:
            print("  (图解交互跳过:", e, ")")
        shot(page, "visualizer_zh")

        print("== 截图：弹窗（充值 / 看广告 / 登录英文）==")
        click_tab(page, "workspace")
        page.wait_for_timeout(500)
        try:
            page.click("#recharge-btn"); page.wait_for_timeout(500)
            shot(page, "modal_recharge_zh", full=False)
            page.click("#recharge-close"); page.wait_for_timeout(300)
        except Exception as e:
            print("  (充值弹窗跳过:", e, ")")
        try:
            page.click("#ad-btn"); page.wait_for_timeout(500)
            shot(page, "modal_ad_zh", full=False)
            page.keyboard.press("Escape"); page.wait_for_timeout(300)
        except Exception as e:
            print("  (广告弹窗跳过:", e, ")")

        ctx.close()
        browser.close()
    print("\n完成，截图在: %s" % OUT)


if __name__ == "__main__":
    main()
