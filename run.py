# -*- coding: utf-8 -*-
"""一键启动入口：本地部署 + 局域网演示。
 
  - 绑定 0.0.0.0，同一局域网的设备（老师/同学的电脑、手机）可访问，便于演示
  - 启动后自动打开浏览器
  - 打印本机局域网 IP，方便把链接发给别人

运行：  python run.py            （需用 Python 3 解释器，见 start.bat）
"""
import socket
import threading
import time
import webbrowser

import uvicorn

HOST = "0.0.0.0"
PORT = 8000


def _lan_ip():
    """获取本机在局域网中的 IP（无网络时回退 127.0.0.1）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _banner():
    ip = _lan_ip()
    line = "=" * 56
    print("\n" + line)
    print("  算法竞赛辅导智能体 ARENA  已启动")
    print(line)
    print("  本机访问：   http://127.0.0.1:%d" % PORT)
    print("  局域网访问： http://%s:%d   (发给老师/同学)" % (ip, PORT))
    print(line + "\n")


def _open_browser():
    time.sleep(2.5)
    webbrowser.open("http://127.0.0.1:%d" % PORT)


if __name__ == "__main__":
    _banner()
    threading.Thread(target=_open_browser, daemon=True).start()
    # 单 worker：SSE 长连接 + SQLite 写入，单进程最稳；演示并发足够
    uvicorn.run("app:app", host=HOST, port=PORT, log_level="info", workers=1)
