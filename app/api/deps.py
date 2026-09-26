"""FastAPI 依赖注入的跨站写防护（2026-09-26 round 28）。

威胁模型：桌面服务监听 127.0.0.1，CORS 挡得住"读响应"，挡不住恶意网页
对 127.0.0.1:8765 发起的 drive-by 写请求（form / no-cors fetch）。
最敏感端点：verify（改判定）、export（写文件）、generate（烧 token）。

策略（对非浏览器客户端零打扰）：
    - Sec-Fetch-Site: cross-site → 403（现代浏览器自动携带，最可靠信号）；
    - 有 Origin 头但 host 不在本地白名单 → 403；
    - 其余（curl / 调度器 / TestClient / 同源）放行。
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


def enforce_same_origin(request: Request) -> None:
    sec_fetch = (request.headers.get("sec-fetch-site") or "").lower()
    if sec_fetch == "cross-site":
        raise HTTPException(403, "拒绝跨站请求（drive-by 防护）。")

    origin = request.headers.get("origin")
    if origin:
        host = (urlparse(origin).hostname or "").lower()
        if host not in _ALLOWED_HOSTS:
            raise HTTPException(403, f"Origin 不受信任：{origin}")
