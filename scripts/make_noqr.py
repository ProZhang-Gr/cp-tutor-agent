# -*- coding: utf-8 -*-
"""从三张海报派生「去掉二维码」版本：剥掉二维码块、把行动召唤居中、网址做成醒目按钮。

生成 *-无码.html 与对应 *_预览.png。源海报不动。
跑：D:/Anaconda3/python.exe scripts/make_noqr.py
"""
import os
import re

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "宣传海报")
SRC = ["ARENA海报-竖版.html", "ARENA海报-功能全景.html", "ARENA海报-五智能体.html"]

EXTRA_CSS = """
/* —— 无二维码版：行动召唤居中、网址做成醒目按钮 —— */
.cta{justify-content:center !important;text-align:center}
.cta-text{max-width:1020px}
.cta-text .u{display:inline-block;border:2px solid var(--teal);border-radius:14px;
  padding:14px 32px;background:rgba(31,111,102,.07);margin-top:20px}
"""


def to_noqr(html):
    # 删掉二维码块（已烘焙为内联 <svg>，块内无嵌套 div，非贪婪匹配到本块 </div>）
    html = re.sub(r'<div class="qr" id="qr">.*?</div>\s*', '', html, count=1, flags=re.S)
    # 末尾追加居中 CSS（覆盖原 space-between 布局）
    html = html.replace("</style>", EXTRA_CSS + "</style>", 1)
    return html


def main():
    outs = []
    for name in SRC:
        src = os.path.join(DIR, name)
        html = open(src, "r", encoding="utf-8").read()
        noqr = to_noqr(html)
        out = os.path.join(DIR, name.replace(".html", "-无码.html"))
        open(out, "w", encoding="utf-8").write(noqr)
        outs.append(out)
        print("  ✅", os.path.basename(out))

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1242, "height": 2208}, device_scale_factor=2)
        page = ctx.new_page()
        for out in outs:
            preview = os.path.splitext(out)[0] + "_预览.png"
            page.goto("file:///" + out.replace("\\", "/"), wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1800)
            page.query_selector(".poster").screenshot(path=preview)
            print("  📸", os.path.basename(preview))
        ctx.close(); b.close()


if __name__ == "__main__":
    main()
