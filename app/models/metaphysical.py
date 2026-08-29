"""术式计算结果表。

对应工程方案：
- 第 6-9 节 Metaphysical Engine（紫微 / 八字 / 六爻 / 梅花 / 奇门 / 掌纹 / 面相）
- 第 54 节 术数引擎测试（Golden Cases）

硬性约束（第 54 节）：
    输入完全相同 → 排盘必须完全相同。
    LLM 解释可以变化，排盘不能变化。

    因此每张表都保存 input_hash，用于 golden case 比对。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class _ChartBase(SQLModel):
    """术式表公共列。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    # 第 54 节：golden case 比对锚点
    input_hash: str = Field(index=True, description="计算输入的 sha256，用于确定性复现验证")

    # 目标时刻（流日/流月/流年或起卦时刻）
    target_date: date = Field(index=True)
    target_time: str = "00:00"

    payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)

    engine_version: str = "unknown"
    engine_name: str = ""
    degraded: bool = Field(
        default=False, description="引擎缺失/降级时为 True，对应 Signal 应跳过而非当作 0"
    )
    degrade_reason: Optional[str] = None

    computed_at: datetime = Field(default_factory=datetime.utcnow)


class ZiweiChart(_ChartBase, table=True):
    """第 6.1 节 紫微斗数（iztro）。

    本命命盘 / 十二宫 / 主星辅星 / 四化 / 大限 / 流年 / 流月 / 流日。
    规则：程序负责排盘，LLM 不允许自己算命盘。
    """

    __tablename__ = "ziwei_charts"

    # 常用查询列（冗余自 payload，便于 SQL 筛选）
    ming_zhu_star: Optional[str] = None
    shen_gong: Optional[str] = None


class BaziChart(_ChartBase, table=True):
    """第 6.1 节 八字 / 历法（lunar-python）。

    四柱 / 五行 / 十神 / 大运 / 流年 / 流月 / 流日。
    """

    __tablename__ = "bazi_charts"

    year_pillar: Optional[str] = None
    month_pillar: Optional[str] = None
    day_pillar: Optional[str] = None
    hour_pillar: Optional[str] = None
    day_master: Optional[str] = Field(default=None, description="日主天干")


class QimenChart(_ChartBase, table=True):
    """第 6.1 节 奇门遁甲（Qimen-Dunjia）。

    九宫 / 九星 / 八门 / 八神 / 阴遁阳遁 / 三元 / 节气 / 格局 / 方向 / 时机。
    V1 优先用于小时级、日级、具体事件。
    """

    __tablename__ = "qimen_charts"

    dun_ju: Optional[str] = Field(default=None, description="遁局，如 阳遁一局")
    zhi_fu: Optional[str] = None


class LiuyaoChart(_ChartBase, table=True):
    """第 6.1 节 六爻（liuyao-divination）。

    纳甲 / 六亲 / 六神 / 世应 / 旺衰 / 空亡 / 暗动 / 化进化退 / 三合六合 / 墓库。
    程序确定性排盘，LLM 负责断卦。
    """

    __tablename__ = "liuyao_charts"

    ben_gua: Optional[str] = Field(default=None, description="本卦")
    bian_gua: Optional[str] = Field(default=None, description="变卦")
    shi_yao: Optional[int] = Field(default=None, description="世爻位置 1-6")


class MeihuaChart(_ChartBase, table=True):
    """第 6.1 节 梅花易数（meihua-yi）。

    时间起卦 / 数字起卦 / 本卦 / 互卦 / 变卦 / 体用 / 五行。
    """

    __tablename__ = "meihua_charts"

    ben_gua: Optional[str] = None
    hu_gua: Optional[str] = None
    bian_gua: Optional[str] = None
    dong_yao: Optional[int] = Field(default=None, description="动爻 1-6")


class PalmFeature(SQLModel, table=True):
    """第 8 节 掌纹系统。

    流程：原图 → MediaPipe 手部关键点 → 透视/角度校正 → 掌纹检测 →
    分类 → 结构化 PalmFeatures → Traditional Palm Rule Engine → PalmSignal

    而不是：照片 → Vision LLM → 直接算命。

    隐私（第 64 节）：原始照片本地保存，不入库、不上传。
    """

    __tablename__ = "palm_features"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)

    hand: str = Field(default="right", description="left / right")
    captured_at: datetime = Field(default_factory=datetime.utcnow)

    # 第 8.1 节 PalmFeatures：结构化几何特征，而非图像
    features: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSON,
        description="{life_line: {length_ratio, continuity, curvature}, head_line: {...}, ...}",
    )

    # 原图只存本地相对路径，绝不入库二进制
    local_image_path: Optional[str] = None

    engine_version: str = "palm-0.1.0"
    degraded: bool = True
    degrade_reason: Optional[str] = "V0.8 未实现"


class FaceFeature(SQLModel, table=True):
    """第 9 节 面相系统。

    照片 → Face Landmark → 结构化几何特征 → 传统面相 Rule Engine → FaceSignal

    禁止由视觉模型从脸推断：医疗情况、智力、犯罪倾向、政治立场、种族、性取向等。
    """

    __tablename__ = "face_features"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    captured_at: datetime = Field(default_factory=datetime.utcnow)

    features: dict[str, Any] = Field(
        default_factory=dict,
        sa_type=JSON,
        description="脸宽高比 / 三庭比例 / 五眼比例 / 额部比例 / 眉眼位置 / 鼻部结构 / 唇部比例 / 下颌形态",
    )

    local_image_path: Optional[str] = None

    engine_version: str = "face-0.1.0"
    degraded: bool = True
    degrade_reason: Optional[str] = "V0.8 未实现"
