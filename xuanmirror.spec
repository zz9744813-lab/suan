# -*- mode: python ; coding: utf-8 -*-
"""玄鉴 XuanMirror 打包配置（PyInstaller）。

用法：
    cd F:/agi/xuanmirror
    pyinstaller --clean --noconfirm xuanmirror.spec

产物：dist/玄鉴XuanMirror.exe（单文件）
数据文件（.env / data/）运行期放 exe 同目录。
"""

from PyInstaller.utils.hooks import collect_submodules

# 前端构建产物 → 打包进 exe，运行期从 _MEIPASS/dist 读取
datas = [("frontend/dist", "dist")]

hiddenimports = []

# uvicorn 动态导入 worker 协议 / 日志
hiddenimports += collect_submodules("uvicorn")

# 术数引擎（适配器内动态 import）
hiddenimports += collect_submodules("iztro_py")
hiddenimports += collect_submodules("lunar_python")

# 序列化 / ORM 动态导入
hiddenimports += collect_submodules("fastapi")
hiddenimports += collect_submodules("pydantic")
hiddenimports += collect_submodules("sqlmodel")

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "ruff"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="玄鉴XuanMirror",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # 保留控制台窗口：可看启动日志、关窗即退出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
