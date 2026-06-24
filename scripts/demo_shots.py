# -*- coding: utf-8 -*-
"""PPT 演示截图：用 Playwright 驱动一个干净的浏览器，按流程自动走查站点，
把第四阶段新增的功能逐屏拍成高清 PNG。

覆盖：中英切换 / 用户画像 / 学习投入 / 成就证书 / 社群 / 算法图解 / 充值·广告弹窗
      + 新手引导 + 系统公告 + 三档主题（舒适/白天/夜间）。

两遍走查：
  Pass A（全新访客，不预设标记）：拍「新手引导」聚光浮层 + 「系统公告」弹窗。
  Pass B（预设标记跳过弹窗）：播种 Pro/签到/埋点/社群数据后，拍主界面中英两版
         + 工作台的白天/夜间两个主题。

目标默认线上 https://cp-tutor-agent.onrender.com；本地可设环境变量
  DEMO_BASE=http://localhost:8000

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
SEEN = ["beta-2026-06", "i18n-incentive-2026-06", "cert-2026-06"]   # 与 guide.js 公告 id 一致

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
    return req.post(BASE + path, data=json.dumps(obj), headers={"Content-Type": "application/json"})

def click_tab(page, view):
    page.click('.tab[data-view="%s"]' % view); page.wait_for_timeout(900)

def toggle_lang(page):
    page.click("#lang-toggle"); page.wait_for_timeout(700)


def pass_a_onboarding(browser):
    """全新访客：新手引导 + 系统公告。"""
    print("== Pass A：新手引导 + 公告（全新访客）==")
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE, wait_until="networkidle", timeout=90000)
    try:
        page.wait_for_selector("#guide-overlay", timeout=10000)
        page.wait_for_timeout(700)
        shot(page, "onboarding_welcome", full=False)
        page.click("#guide-next"); page.wait_for_timeout(600)   # ① 选题
        page.click("#guide-next"); page.wait_for_timeout(600)   # ② 分析
        page.click("#guide-next"); page.wait_for_timeout(700)   # ③ 代码区（聚光）
        shot(page, "onboarding_spotlight", full=False)
        for _ in range(len(SEEN) + 8):                          # 点到结束触发公告
            if not page.query_selector("#guide-overlay"):
                break
            page.click("#guide-next"); page.wait_for_timeout(350)
        page.wait_for_selector("#announce-modal:not(.hidden)", timeout=8000)
        page.wait_for_timeout(500)
        shot(page, "announcement", full=False)
    except Exception as e:
        print("  (Pass A 跳过:", e, ")")
    ctx.close()


def pass_b_tour(browser):
    """预设标记跳过弹窗，播种数据后走查主界面 + 主题。"""
    print("== Pass B：主走查（中英 + 主题）==")
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    ctx.add_init_script(
        "try{localStorage.setItem('cp_onboarded_v1','1');"
        "localStorage.setItem('cp_announce_seen', JSON.stringify(%s));}catch(e){}" % json.dumps(SEEN))
    req = ctx.request

    print("  -- 播种数据（HTTP API）--")
    print("  注册:", jpost(req, "/api/register", {"username": U, "password": PW}).status)
    jpost(req, "/api/recharge", {"yuan": 30})
    jpost(req, "/api/checkin", {})
    jpost(req, "/api/telemetry", {"problem_id": "P1", "active_seconds": 1500, "keystrokes": 820, "runs": 6, "submits": 3})
    jpost(req, "/api/telemetry", {"problem_id": "P2", "active_seconds": 1100, "keystrokes": 540, "runs": 4, "submits": 2})
    jpost(req, "/api/community/posts", {"tag": "题解", "title": "单调栈 O(n) 解接雨水",
          "body": "维护一个高度递减的单调栈，遇到更高的柱子就出栈结算每一层能接的水，整体 O(n)。"})
    jpost(req, "/api/community/posts", {"tag": "求助", "title": "二分边界总差一怎么办",
          "body": "闭区间 [lo,hi] 用 lo<=hi，命中即返回，否则收缩区间；建议一套写法用到底不要混。"})

    page = ctx.new_page()
    page.goto(BASE, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(1200)
    try:
        page.fill("#problem-input", SAMPLE_PROBLEM)
    except Exception as e:
        print("  (填题跳过:", e, ")")
    page.wait_for_timeout(400)

    print("  -- 工作台 中文（舒适主题）--")
    shot(page, "workspace_zh")

    print("  -- 三档主题：白天 / 夜间 --")
    page.click("#theme-toggle"); page.wait_for_timeout(500)     # comfort -> light
    shot(page, "theme_light")
    page.click("#theme-toggle"); page.wait_for_timeout(500)     # light -> dark
    shot(page, "theme_dark")
    page.click("#theme-toggle"); page.wait_for_timeout(400)     # dark -> comfort

    print("  -- 工作台 英文 --")
    toggle_lang(page)
    shot(page, "workspace_en")

    print("  -- 仪表盘 英 / 中 --")
    click_tab(page, "dashboard"); page.wait_for_timeout(1000)
    shot(page, "dashboard_en")
    for sel, nm in [("#profile-card", "profile_card_en"),
                    ("#engage-card", "engage_card_en"),
                    ("#ach-card", "ach_card_en")]:
        try:
            page.locator(sel).screenshot(path=os.path.join(OUT, "el_%s.png" % nm))
            print("  📸 el_%s.png" % nm)
        except Exception as e:
            print("  (特写跳过 %s: %s)" % (nm, e))
    toggle_lang(page); page.wait_for_timeout(700)
    shot(page, "dashboard_zh")
    # 仪表盘夜间主题特写
    page.click("#theme-toggle"); page.click("#theme-toggle"); page.wait_for_timeout(600)  # -> dark
    shot(page, "dashboard_dark")
    page.click("#theme-toggle"); page.wait_for_timeout(300)     # back comfort

    print("  -- 社群 中 / 英 --")
    click_tab(page, "community"); page.wait_for_timeout(1000)
    shot(page, "community_zh")
    toggle_lang(page); page.wait_for_timeout(800)
    shot(page, "community_en")
    toggle_lang(page)

    print("  -- 算法图解 --")
    click_tab(page, "visualizer"); page.wait_for_timeout(700)
    try:
        page.locator("#vz-list >*").first.click(); page.wait_for_timeout(800)
        page.click("#vz-next"); page.wait_for_timeout(400)
        page.click("#vz-next"); page.wait_for_timeout(400)
    except Exception as e:
        print("  (图解交互跳过:", e, ")")
    shot(page, "visualizer_zh")

    print("  -- 弹窗：公告 / 充值 / 看广告 --")
    click_tab(page, "workspace"); page.wait_for_timeout(400)
    for sel, close, nm in [("#announce-btn", "#announce-close", "modal_announce"),
                           ("#recharge-btn", "#recharge-close", "modal_recharge"),
                           ("#ad-btn", None, "modal_ad")]:
        try:
            page.click(sel); page.wait_for_timeout(500)
            shot(page, nm, full=False)
            if close:
                page.click(close)
            else:
                page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception as e:
            print("  (%s 跳过: %s)" % (nm, e))
    ctx.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pass_a_onboarding(browser)
        pass_b_tour(browser)
        browser.close()
    print("\n完成，截图在: %s" % OUT)


if __name__ == "__main__":
    main()
