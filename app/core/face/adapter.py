"""FaceAdapter —— 面相信号。

对应工程方案：
- 第 9 节 面相系统（照片 → Face Landmark → 结构化几何特征 → Rule Engine → FaceSignal）
- 第 14 节 统一 Signal Schema
- 第 57 节 时间尺度约束（面相：不使用 日/周，弱 月/年）

CV 实现见 cv.py（Haar 级联 + 几何测量）。

第 9 节硬性禁止：
    不得由视觉模型从脸推断医疗情况、智力、犯罪倾向、政治立场、
    种族、性取向等敏感事实属性。本 Adapter 只消费几何比例。

隐私（第 64 节）：原始照片仅本地。
"""

from __future__ import annotations

from typing import Any

from app.core.base import AdapterQuery, MetaphysicalAdapter, registry
from app.schemas.signal import (
    Evidence,
    EvidenceSource,
    Signal,
    SourceType,
)

from .cv import extract_face_features

ENGINE_VERSION = "face-0.1.0"


class FaceAdapter(MetaphysicalAdapter):
    source = SourceType.FACE
    engine_name = "face-cv"
    engine_version = ENGINE_VERSION

    @property
    def available(self) -> bool:
        try:
            import cv2  # noqa: F401

            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        """从本地照片提取 FaceFeatures（第 9 节）。"""
        if not query.image_path:
            return {}
        try:
            features = extract_face_features(query.image_path)
        except Exception:
            return {}
        return features.to_dict()

    # ------------------------------------------------------------------
    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        """几何特征 → Signal。

        规则（骨架，待验证）：
            三庭比例均衡 → 正向基础；明显失衡 → 负向。
            仅输出几何比例信号，绝不输出人格/属性推断（第 9 节禁止）。
        """
        if not chart.get("detected"):
            return []

        halves = chart.get("three_halves", {})
        upper = halves.get("upper", 1 / 3)
        middle = halves.get("middle", 1 / 3)
        lower = halves.get("lower", 1 / 3)

        # 均衡度：三庭与 1/3 的偏差
        imbalance = abs(upper - 1 / 3) + abs(middle - 1 / 3) + abs(lower - 1 / 3)
        balanced = imbalance < 0.15

        rule_id = f"FACE-R-threehalves-{query.domain.value}"
        return [
            Signal(
                **self._base_signal_kwargs(query),
                direction=1.0 if balanced else -1.0,
                strength=round(0.2 + max(0, 0.3 - imbalance), 3),  # 弱信号（第 57 节）
                confidence=0.25,
                evidence=[
                    Evidence(
                        source=EvidenceSource.TRADITIONAL_RULE,
                        rule_id=rule_id,
                        description=(
                            f"三庭比例 上{upper:.2f}/中{middle:.2f}/下{lower:.2f}"
                            f"（失衡度 {imbalance:.2f}），"
                            f"脸宽高比 {chart.get('face_width_height_ratio', 0):.2f}"
                        ),
                    )
                ],
                counter_evidence=(
                    [
                        Evidence(
                            source=EvidenceSource.TRADITIONAL_RULE,
                            rule_id=rule_id,
                            description=f"三庭明显失衡（{imbalance:.2f}）",
                        )
                    ]
                    if not balanced
                    else []
                ),
                rule_ids=[rule_id],
                dependency_group=None,
            )
        ]


registry.register(FaceAdapter())
