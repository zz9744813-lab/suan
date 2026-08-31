"""玄鉴 XuanMirror 桌面启动器 —— PyInstaller 打包入口。

双击 exe 后自动完成：
    1. 切换到 exe 所在目录（让 .env / data/ 相对路径正确）
    2. 启动后端 FastAPI（127.0.0.1:8765，服务前端静态文件）
    3. 自动打开浏览器

数据文件（.env、data/）持久化在 exe 同目录，升级 exe 不影响数据。
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def _base_dir() -> str:
    """exe 同目录（打包后）或脚本目录（开发时）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _open_browser(delay: float = 1.5) -> None:
    """等服务器起来后自动打开浏览器。"""
    time.sleep(delay)
    try:
        webbrowser.open(URL)
    except Exception:
        pass


def main() -> None:
    base = _base_dir()

    # 数据目录切到 exe 同目录，保证 .env 与 SQLite 可持久化、可编辑
    os.chdir(base)
    os.makedirs(os.path.join(base, "data"), exist_ok=True)

    # 若同目录没有 .env，则用一个最小示例（提示用户填 API key）
    env_path = os.path.join(base, ".env")
    if not os.path.exists(env_path):
        _write_example_env(env_path)

    print(f"玄鉴 XuanMirror 启动中… 稍后自动打开浏览器 {URL}")
    print("若未自动打开，请手动访问上面的地址。")

    threading.Thread(target=_open_browser, daemon=True).start()

    # 直接 import app 对象（而非 uvicorn 字符串 "app.main:app"），
    # 让 PyInstaller 能静态发现并打包 app 包。
    import uvicorn
    from app.main import app as fastapi_app

    uvicorn.run(
        fastapi_app,
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=False,
    )


def _write_example_env(path: str) -> None:
    """首次运行生成 .env 示例（不含密钥，提示用户自行配置）。"""
    example = (
        "# 玄鉴 XuanMirror 配置（示例）\n"
        "# 在下面填入你的 LLM 中转站 / API 信息后重启本程序即可生效。\n\n"
        "# 推理层（命理批示等）\n"
        "REASONING_BASE_URL=\n"
        "REASONING_API_KEY=\n"
        "REASONING_MODEL=\n\n"
        "# 廉价层（信号格式化等）\n"
        "CHEAP_BASE_URL=\n"
        "CHEAP_API_KEY=\n"
        "CHEAP_MODEL=\n\n"
        "# 视觉层（掌纹/面相，可留空）\n"
        "VISION_BASE_URL=\n"
        "VISION_API_KEY=\n"
        "VISION_MODEL=\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(example)


if __name__ == "__main__":
    main()
