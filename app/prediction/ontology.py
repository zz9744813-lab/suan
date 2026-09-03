"""Event Ontology —— 预测领域词典。

对应工程方案第 56 节：

    所有事件使用 Event Ontology。

    避免每次 LLM 发明不同说法。

事件类型格式：<domain>.<event>
每个事件类型都必须可观测、可记录、可判定「是否发生」。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventSpec:
    """一个事件类型的定义。"""

    event_type: str
    domain: str
    label: str
    # 默认成功标准（候选生成时的起点，冻结前必须细化）
    success_criteria: tuple[str, ...]
    failure_criteria: tuple[str, ...]
    # 默认评分规则（第 18 节：必须在冻结前确定）
    grading_rule: str = "二值：发生=1.0，未发生=0.0"
    # 适合的时间尺度（第 57 节）
    preferred_scales: tuple[str, ...] = ("day",)


ONTOLOGY: dict[str, EventSpec] = {
    # ---------------- career ----------------
    "career.unexpected_task": EventSpec(
        event_type="career.unexpected_task",
        domain="career",
        label="临时工作安排",
        success_criteria=(
            "出现至少一次非前一日已计划的工作任务",
            "导致原计划改变 ≥ 30 分钟",
        ),
        failure_criteria=("没有发生", "虽有沟通但未改变计划"),
        preferred_scales=("day",),
    ),
    "career.role_change": EventSpec(
        event_type="career.role_change",
        domain="career",
        label="岗位职责变化",
        success_criteria=("收到明确的职责/岗位调整通知",),
        failure_criteria=("未收到任何调整通知",),
        preferred_scales=("week", "month"),
    ),
    "career.job_offer": EventSpec(
        event_type="career.job_offer",
        domain="career",
        label="收到工作机会",
        success_criteria=("收到明确的录用意向或面试邀请",),
        failure_criteria=("未收到",),
        preferred_scales=("week", "month"),
    ),
    "career.conflict": EventSpec(
        event_type="career.conflict",
        domain="career",
        label="工作冲突",
        success_criteria=("发生明确的分歧或争执",),
        failure_criteria=("未发生",),
        preferred_scales=("day", "week"),
    ),
    # ---------------- money ----------------
    "money.unplanned_expense": EventSpec(
        event_type="money.unplanned_expense",
        domain="money",
        label="计划外支出",
        success_criteria=("发生当日凌晨未计划的支出", "金额 ≥ 50 元"),
        failure_criteria=("无计划外支出",),
        preferred_scales=("day",),
    ),
    "money.income": EventSpec(
        event_type="money.income",
        domain="money",
        label="收入到账",
        success_criteria=("收到非固定工资的收入",),
        failure_criteria=("未收到",),
        preferred_scales=("week", "month"),
    ),
    "money.large_purchase": EventSpec(
        event_type="money.large_purchase",
        domain="money",
        label="大额消费",
        success_criteria=("单笔支出 ≥ 1000 元",),
        failure_criteria=("未发生",),
        preferred_scales=("week", "month"),
    ),
    # ---------------- social ----------------
    "social.new_contact": EventSpec(
        event_type="social.new_contact",
        domain="social",
        label="结识新联系人",
        success_criteria=("与全新对象发生首次实质性交流",),
        failure_criteria=("未发生",),
        preferred_scales=("day", "week"),
    ),
    "social.old_contact": EventSpec(
        event_type="social.old_contact",
        domain="social",
        label="旧联系人主动联系",
        success_criteria=("非高频联系人主动发起联系",),
        failure_criteria=("未收到",),
        preferred_scales=("day",),
    ),
    "social.conflict": EventSpec(
        event_type="social.conflict",
        domain="social",
        label="人际冲突",
        success_criteria=("发生明确的不愉快或争执",),
        failure_criteria=("未发生",),
        preferred_scales=("day", "week"),
    ),
    # ---------------- study ----------------
    "study.study_session": EventSpec(
        event_type="study.study_session",
        domain="study",
        label="主动学习",
        success_criteria=("主动学习 ≥ 30 分钟",),
        failure_criteria=("未学习或不足 30 分钟",),
        preferred_scales=("day",),
    ),
    "study.goal_complete": EventSpec(
        event_type="study.goal_complete",
        domain="study",
        label="学习目标达成",
        success_criteria=("完成预设的学习目标",),
        failure_criteria=("未完成",),
        preferred_scales=("week", "month"),
    ),
    # ---------------- project ----------------
    "project.new_project": EventSpec(
        event_type="project.new_project",
        domain="project",
        label="启动新项目",
        success_criteria=("正式开始一个此前未启动的项目",),
        failure_criteria=("未启动",),
        preferred_scales=("week", "month"),
    ),
    "project.delay": EventSpec(
        event_type="project.delay",
        domain="project",
        label="项目延期",
        success_criteria=("已定计划发生延期",),
        failure_criteria=("按期推进",),
        preferred_scales=("week", "month"),
    ),
    "project.milestone": EventSpec(
        event_type="project.milestone",
        domain="project",
        label="项目里程碑达成",
        success_criteria=("达成一个预设里程碑",),
        failure_criteria=("未达成",),
        preferred_scales=("week", "month"),
    ),
    # ---------------- schedule / unexpected ----------------
    "schedule.disruption": EventSpec(
        event_type="schedule.disruption",
        domain="schedule",
        label="日程被打乱",
        success_criteria=("当日计划发生 ≥ 30 分钟的偏离",),
        failure_criteria=("计划基本按期执行",),
        preferred_scales=("day",),
    ),
    "unexpected_event.major": EventSpec(
        event_type="unexpected_event.major",
        domain="unexpected_event",
        label="重大意外事件",
        success_criteria=("发生需要临时应对的重大事件",),
        failure_criteria=("未发生",),
        preferred_scales=("day", "week"),
    ),
    # ---------------- relationship（姻缘/感情）----------------
    "relationship.romantic_encounter": EventSpec(
        event_type="relationship.romantic_encounter",
        domain="relationship",
        label="遇到心动的缘分",
        success_criteria=(
            "出现一次明确的好感信号：新认识并产生好感的异性/旧识升温/被介绍对象，任一种",
            "你能在睡前复述出这次接触的对象和经过",
        ),
        failure_criteria=("没有任何此类接触或迹象",),
        preferred_scales=("day", "week"),
    ),
    "relationship.relationship_progress": EventSpec(
        event_type="relationship.relationship_progress",
        domain="relationship",
        label="感情关系推进",
        success_criteria=(
            "与心上人/伴侣的关系有明确推进：单独约会、互表心意、确定关系或深度谈心，任一种",
        ),
        failure_criteria=("关系原地踏步", "尚无在意的对象，无推进对象"),
        preferred_scales=("week", "month"),
    ),
    "relationship.rival_or_misunderstanding": EventSpec(
        event_type="relationship.rival_or_misunderstanding",
        domain="relationship",
        label="感情波折（误会/争执）",
        success_criteria=("与心仪对象或伴侣发生明显争执、误会或冷战",),
        failure_criteria=("未发生", "无感情对象可争执"),
        preferred_scales=("week",),
    ),
    # ---------------- 贵人/聚会 ----------------
    "career.noble_help": EventSpec(
        event_type="career.noble_help",
        domain="career",
        label="获得实质帮助",
        success_criteria=(
            "工作/学业上收到明确的具体帮助：前辈指点、资源介绍、替你说话或替你解围",
        ),
        failure_criteria=("未获得任何此类帮助",),
        preferred_scales=("day", "week"),
    ),
    "social.gathering": EventSpec(
        event_type="social.gathering",
        domain="social",
        label="聚会/饭局邀约",
        success_criteria=("收到或参加一次非独自的聚会/饭局/集体活动",),
        failure_criteria=("没有任何聚会或邀约",),
        preferred_scales=("day", "week"),
    ),
    # ---------------- communication / habit / travel ----------------
    "communication.message_volume_spike": EventSpec(
        event_type="communication.message_volume_spike",
        domain="communication",
        label="消息量激增",
        success_criteria=("沟通条数明显高于近期日均",),
        failure_criteria=("持平或更低",),
        preferred_scales=("day",),
    ),
    "habit.break": EventSpec(
        event_type="habit.break",
        domain="habit",
        label="习惯中断",
        success_criteria=("既定习惯当日未执行",),
        failure_criteria=("习惯正常执行",),
        preferred_scales=("day",),
    ),
    "travel.trip": EventSpec(
        event_type="travel.trip",
        domain="travel",
        label="出行",
        success_criteria=("发生跨城或长途出行",),
        failure_criteria=("未出行",),
        preferred_scales=("week", "month"),
    ),
}


def get_spec(event_type: str) -> EventSpec | None:
    return ONTOLOGY.get(event_type)


def by_domain(domain: str) -> list[EventSpec]:
    return [s for s in ONTOLOGY.values() if s.domain == domain]


def by_scale(scale: str) -> list[EventSpec]:
    return [s for s in ONTOLOGY.values() if scale in s.preferred_scales]


def all_event_types() -> list[str]:
    return sorted(ONTOLOGY)
