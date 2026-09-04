"""影像相学分析接口测试（隐私边界是测试重点）。

- 合法图片 → 200，特征结构完整，原图临时文件必须被删除；
- 非法 kind → 400；非法 MIME → 415；过大 → 413；
- 未勾选云端 → cloud.used=False，且不发任何网络请求（默认本地优先）。
"""

from __future__ import annotations

import io as _io

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np


def _jpg_bytes() -> bytes:
    """造一张可用 JPEG（白底 + 几何线条，让 CV 有内容可看）。"""
    img = np.full((240, 240, 3), 235, dtype=np.uint8)
    cv2.line(img, (30, 60), (210, 90), (60, 60, 60), 3)
    cv2.line(img, (30, 120), (200, 130), (60, 60, 60), 3)
    cv2.line(img, (40, 180), (190, 170), (60, 60, 60), 3)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _post(client, kind: str = "palm", data: bytes | None = None, mime: str = "image/jpeg"):
    files = {"file": ("t.jpg", _io.BytesIO(data if data is not None else _jpg_bytes()), mime)}
    return client.post("/api/imaging/analyze", files=files, data={"kind": kind})


def test_palm_analyze_ok_and_image_deleted(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.imaging.UPLOAD_DIR", tmp_path / "uploads")
    resp = _post(client, "palm")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "palm"
    assert "detected" in body and isinstance(body["reading"], list) and body["reading"]
    # 隐私铁律：临时图已被删除，云端未发送
    assert list((tmp_path / "uploads").glob("*")) == []
    assert body["privacy"]["original_deleted"] is True
    assert body["privacy"]["cloud_sent"] is False
    assert body["cloud"]["used"] is False


def test_face_analyze_ok(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.imaging.UPLOAD_DIR", tmp_path / "uploads")
    resp = _post(client, "face")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "face"
    assert isinstance(body["features"], dict)
    assert list((tmp_path / "uploads").glob("*")) == []


def test_reject_bad_kind(client):
    resp = _post(client, "iris")
    assert resp.status_code == 400


def test_reject_bad_mime(client):
    resp = _post(client, "palm", data=b"x" * 64, mime="text/plain")
    assert resp.status_code == 415


def test_reject_oversize(client, monkeypatch):
    monkeypatch.setattr("app.services.imaging.MAX_BYTES", 128)
    resp = _post(client, "palm", data=b"x" * 256)
    assert resp.status_code == 413
