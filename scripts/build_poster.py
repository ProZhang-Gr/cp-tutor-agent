# -*- coding: utf-8 -*-
"""把站内二维码库算出的点阵，烘焙成一段矢量 SVG 注入海报，并截一张高清预览图。

- 二维码用 static/qrcode.min.js（qrcode-generator）现算，输出内联 SVG <path>，
  海报因此自包含、矢量、打印清晰，且不在可编辑文件里塞 56KB 的库。
- 改了海报里的网址后重跑本脚本即可重新生成二维码。

跑：D:/Anaconda3/python.exe scripts/build_poster.py
依赖：playwright（已装）
"""
import os
import re

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QR_JS = os.path.join(ROOT, "static", "qrcode.min.js")
POSTER = os.path.join(ROOT, "宣传海报", "ARENA海报-竖版.html")
PREVIEW = os.path.join(ROOT, "宣传海报", "ARENA海报-竖版_预览.png")
URL = "https://cp-tutor-agent.onrender.com"
QUIET = 2          # 二维码静区（模块数）
DARK = "#1b1712"   # 暖墨色码点，保证扫描对比度


def qr_matrix(page):
    js = open(QR_JS, "r", encoding="utf-8").read()
    page.set_content("<!doctype html><html><body></body></html>")
    page.add_script_tag(content=js)
    return page.evaluate(
        """(url)=>{var q=qrcode(0,'M');q.addData(url);q.make();
        var n=q.getModuleCount(),g=[];for(var r=0;r<n;r++){var row=[];
        for(var c=0;c<n;c++)row.push(q.isDark(r,c)?1:0);g.push(row);}
        return {n:n,g:g};}""", URL)


def build_svg(n, grid):
    parts = []
    for r in range(n):
        row = grid[r]
        for c in range(n):
            if row[c]:
                parts.append("M%d %dh1v1h-1z" % (c, r))
    vb = "%d %d %d %d" % (-QUIET, -QUIET, n + 2 * QUIET, n + 2 * QUIET)
    return ('<svg viewBox="%s" shape-rendering="crispEdges" '
            'xmlns="http://www.w3.org/2000/svg">'
            '<rect x="%d" y="%d" width="%d" height="%d" fill="#ffffff"/>'
            '<path d="%s" fill="%s"/></svg>') % (
        vb, -QUIET, -QUIET, n + 2 * QUIET, n + 2 * QUIET, "".join(parts), DARK)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1242, "height": 2208}, device_scale_factor=2)
        page = ctx.new_page()

        m = qr_matrix(page)
        svg = build_svg(m["n"], m["g"])
        print("  二维码模块数 =", m["n"], "x", m["n"])

        html = open(POSTER, "r", encoding="utf-8").read()
        # 把占位（<!--QR--> + fallback）整段替换为生成的 SVG
        html2 = re.sub(r"<!--QR-->.*?</div>\s*(?=</div>)", svg, html, count=1, flags=re.S)
        if html2 == html:
            print("  !! 未找到二维码占位符，跳过注入")
        else:
            open(POSTER, "w", encoding="utf-8").write(html2)
            print("  ✅ 二维码已注入海报")

        # 截高清预览
        page.goto("file:///" + POSTER.replace("\\", "/"), wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1800)   # 等 Google 字体加载
        el = page.query_selector(".poster")
        el.screenshot(path=PREVIEW)
        print("  📸 预览：", PREVIEW)

        ctx.close(); b.close()


if __name__ == "__main__":
    main()
