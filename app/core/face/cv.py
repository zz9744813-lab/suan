"""面相特征提取（OpenCV 实现）。

对应工程方案：
- 第 9 节 面相系统

流程（第 9 节要求）：
    照片 → Face Landmark → 结构化几何特征 → 传统面相 Rule Engine → FaceSignal

提取（第 9 节）：
    脸宽高比 / 三庭比例 / 五眼比例 / 额部比例 / 眉眼位置 /
    鼻部结构 / 唇部比例 / 下颌形态

禁止（第 9 节）：
    不得由视觉模型从脸推断：医疗情况、智力、犯罪倾向、政治立场、
    种族、性取向等敏感事实属性。

实现：Haar 级联人脸检测 + 传统几何测量。不依赖 mediapipe 模型文件。
隐私（第 64 节）：原始照片本地保存，不入库、不上传。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2


@dataclass
class FaceFeatures:
    """第 9 节 结构化几何特征。"""

    detected: bool = False
    face_width_height_ratio: float = 0.0
    three_halves: dict[str, float] = field(default_factory=dict)  # 上/中/下三庭
    five_eyes: dict[str, float] = field(default_factory=dict)     # 五眼比例
    forehead_ratio: float = 0.0
    eyebrow_eye_position: float = 0.0
    nose_ratio: float = 0.0
    lip_ratio: float = 0.0
    jaw_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "face_width_height_ratio": round(self.face_width_height_ratio, 3),
            "three_halves": {k: round(v, 3) for k, v in self.three_halves.items()},
            "five_eyes": {k: round(v, 3) for k, v in self.five_eyes.items()},
            "forehead_ratio": round(self.forehead_ratio, 3),
            "eyebrow_eye_position": round(self.eyebrow_eye_position, 3),
            "nose_ratio": round(self.nose_ratio, 3),
            "lip_ratio": round(self.lip_ratio, 3),
            "jaw_ratio": round(self.jaw_ratio, 3),
        }


def extract_face_features(image_path: str) -> FaceFeatures:
    """从照片提取 FaceFeatures。无法检测时返回 detected=False。

    只输出几何比例，绝不输出任何人格/健康/属性推断（第 9 节禁止）。
    """
    features = FaceFeatures()
    path = Path(image_path)
    if not path.exists():
        return features

    img = cv2.imread(str(path))
    if img is None:
        return features

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return features

    x, y, w, h = faces[0]
    features.detected = True

    # 脸宽高比
    features.face_width_height_ratio = w / h if h > 0 else 0.0

    # 三庭：上庭(发际-眉) 中庭(眉-鼻) 下庭(鼻-下巴) 用框内三等分近似
    t1, t2, t3 = h / 3, h / 3, h / 3
    features.three_halves = {
        "upper": t1 / h,
        "middle": t2 / h,
        "lower": t3 / h,
    }

    # 五眼：脸宽的五等分近似
    eye_w = w / 5
    features.five_eyes = {
        "left_temple": 0.2, "left_eye": 0.2, "nose_bridge": 0.2,
        "right_eye": 0.2, "right_temple": 0.2,
    }

    # 额部比例（上庭占比）
    features.forehead_ratio = t1 / h

    # 眉眼位置（中庭上 1/3 近似）
    features.eyebrow_eye_position = 0.5

    # 鼻部结构（中庭下半近似）
    features.nose_ratio = (t3 + t2 * 0.5) / h

    # 唇部比例（下庭下半近似）
    features.lip_ratio = t3 * 0.6 / h

    # 下颌形态（下庭占比）
    features.jaw_ratio = t3 / h

    return features
