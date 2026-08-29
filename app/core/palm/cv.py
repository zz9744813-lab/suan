"""掌纹特征提取（OpenCV 实现）。

对应工程方案：
- 第 8 节 掌纹系统

流程（第 8 节要求）：
    原图 → 关键点检测 → 透视/角度校正 → 掌纹检测 → 分类 →
    长度/曲率/断点/深度特征 → 结构化 PalmFeatures

而不是：照片 → Vision LLM → 直接算命

实现说明：
    使用 OpenCV 传统 CV（肤色分割 + 手部轮廓 + 掌纹线边缘检测），
    不依赖 mediapipe 模型文件。输出第 8.1 节格式的结构化特征。

隐私（第 64 节）：
    原始照片本地保存，不入库、不上传。本模块只输出数值特征。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class PalmFeatures:
    """第 8.1 节 PalmFeatures 结构化输出。"""

    life_line: dict[str, float] = field(default_factory=dict)
    head_line: dict[str, float] = field(default_factory=dict)
    heart_line: dict[str, float] = field(default_factory=dict)
    hand_ratio: float = 0.0
    palm_width_ratio: float = 0.0
    detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "life_line": self.life_line,
            "head_line": self.head_line,
            "heart_line": self.heart_line,
            "hand_ratio": round(self.hand_ratio, 3),
            "palm_width_ratio": round(self.palm_width_ratio, 3),
            "detected": self.detected,
        }


def extract_palm_features(image_path: str) -> PalmFeatures:
    """从掌纹照片提取 PalmFeatures。

    无法检测时返回 detected=False 的空特征（调用方应降级，不硬猜）。
    """
    features = PalmFeatures()
    path = Path(image_path)
    if not path.exists():
        return features

    img = cv2.imread(str(path))
    if img is None:
        return features

    # 1. 肤色分割（YCrCb 空间）提取手部
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    skin = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))

    contours, _ = cv2.findContours(skin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return features

    hand = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(hand)
    img_area = img.shape[0] * img.shape[1]
    if area / img_area < 0.03:
        return features  # 肤色区域太小，不是手掌

    # 2. 手型比例
    x, y, w, h = cv2.boundingRect(hand)
    features.hand_ratio = w / h if h > 0 else 0.0
    features.palm_width_ratio = w / img.shape[1] if img.shape[1] > 0 else 0.0

    # 3. 掌纹线（ROI 内 Canny 边缘 → 最长线段的长度/曲率/连续性近似）
    roi = img[y : y + h, x : x + w]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    edges = cv2.Canny(blurred, 40, 120)

    # 用形态学连接掌纹线
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    # 按角度分三组线（生命线/智慧线/感情线的近似方向）
    features.life_line = _measure_line_group(edges, vertical=True, img_h=h)
    features.head_line = _measure_line_group(edges, vertical=False, img_h=h)
    features.heart_line = _measure_line_group(edges, vertical=False, img_h=h, upper=True)

    features.detected = True
    return features


def _measure_line_group(
    edges: np.ndarray, *, vertical: bool, img_h: int, upper: bool = False
) -> dict[str, float]:
    """测量一组掌纹线的长度比/曲率/连续性（近似）。"""
    h, w = edges.shape
    roi = edges[: h // 2, :] if upper else edges

    # 投影统计线密度
    if vertical:
        density = roi.sum(axis=0)
    else:
        density = roi.sum(axis=1)

    nz = [i for i, v in enumerate(density) if v > 0]
    if not nz:
        return {}

    span = nz[-1] - nz[0]
    length_ratio = min(1.0, span / max(1, img_h if vertical else w))

    # 曲率：线密度的标准差（波动大 → 曲率大）
    vals = [density[i] for i in nz]
    mean_v = sum(vals) / len(vals) if vals else 0
    std = (sum((v - mean_v) ** 2 for v in vals) / len(vals)) ** 0.5 if vals else 0
    curvature = min(1.0, std / 50.0)

    # 连续性：非零区间的占比
    continuity = min(1.0, len(nz) / max(1, span + 1))

    return {
        "length_ratio": round(length_ratio, 3),
        "continuity": round(continuity, 3),
        "curvature": round(curvature, 3),
    }
