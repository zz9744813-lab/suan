"""API 路由汇总。

    /api/predictions/*   预测生成 / 详情 / 验证 / 历史
    /api/analytics/*     评分 / 校准 / 可靠度矩阵 / 消融
    /api/system/*        引擎状态 / 用户档案 / 规则 / 本体 / Gate 测试
"""

from . import analytics, predictions, system

__all__ = ["predictions", "analytics", "system"]
