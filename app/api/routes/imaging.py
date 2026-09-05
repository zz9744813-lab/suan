"""影像相学分析路由（第 8/9/64 节）。

POST /api/imaging/analyze —— 上传面相/掌纹照片，本地 CV 分析，
可选（用户当次勾选）云端视觉详批。隐私边界见 app/services/imaging.py。
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.services import imaging

router = APIRouter()


@router.post("/imaging/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    kind: str = Form(...),
    use_cloud: bool = Form(False),
) -> JSONResponse:
    kind = kind.strip().lower()
    if kind not in ("palm", "face"):
        return JSONResponse({"detail": "kind 必须是 palm 或 face"}, status_code=400)

    mime = (file.content_type or "").lower()
    ext = imaging.ALLOWED_TYPES.get(mime)
    if not ext:
        return JSONResponse(
            {"detail": "仅支持 JPEG / PNG / WebP 图片"}, status_code=415
        )

    # 大小预检：Starlette 会把超大 body 落盘缓冲，先按声明体积拒绝，
    # 避免把整个文件读进内存后才发现超限（声明缺失时仍以读后实际大小为准）。
    declared = getattr(file, "size", None)
    if declared is not None and declared > imaging.MAX_BYTES:
        return JSONResponse({"detail": "图片不能超过 8MB"}, status_code=413)

    data = await file.read()
    if not data:
        return JSONResponse({"detail": "文件为空"}, status_code=400)
    if len(data) > imaging.MAX_BYTES:
        return JSONResponse({"detail": "图片不能超过 8MB"}, status_code=413)

    # 本地确定性分析（CV，不上云；原图分析后立即删除）
    try:
        local = imaging.analyze_local(data, ext, kind)
    except Exception as exc:  # CV 管线异常要降级为可读错误，不能 500 裸奔
        return JSONResponse(
            {"detail": f"图像分析失败：{type(exc).__name__}"}, status_code=422
        )

    # 云端详批：仅当用户当次勾选。失败不阻塞本地结果。
    cloud: dict = {"used": False}
    if use_cloud:
        cloud = imaging.cloud_reading(data, mime, kind)

    return JSONResponse(
        {
            "kind": kind,
            "detected": local["detected"],
            "features": local["features"],
            "reading": local["reading"],
            "cloud": cloud,
            "privacy": {
                "original_deleted": True,
                "stored": False,
                "cloud_sent": bool(cloud.get("used")),
                "note": (
                    "原图已在分析完成后立即删除，特征结果不入库；"
                    "云端详批仅在你勾选时发送原图。"
                ),
            },
        }
    )
