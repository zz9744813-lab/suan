"""事件叙事注册表 —— 让每个预测「言之有物」。

对应工程方案第 56 节：Ontology 保证可证伪（成败标准）；
本模块负责把可证伪的事件骨架渲染成「何时、何事、何景、何据、何策」的
完整叙事（描述层），并明确标出术式依据与幸运元素。

硬性约束：
- 描述中的「依据」只能来自真实收集到的 Signal.evidence（传统规则层），
  不得凭空编造星曜/卦象（第 55 节：禁止把推测伪装成传统规则事实）。
- 概率/「交叉印证」数量只陈述事实，不作效力断言（C-006）。
- 「幸运元素」是传统民俗参考，不构成任何功利承诺。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventNarrative:
    """一个事件类型的叙事素材。各字段可以是带 {when}/{domain_ctx} 占位的句子。"""

    # 事件可能的具体形态（2~4 条，供挑选/组合）
    scenarios: tuple[str, ...]
    # 行动建议（一句具体可做的事）
    advice: str
    # 注意事项（负向/反方信号存在时强调）
    caution: str


NARRATIVES: dict[str, EventNarrative] = {
    # ------------------------------------------------ career
    "career.unexpected_task": EventNarrative(
        scenarios=(
            "现场临时加派任务（验收、迎检、资料补做）",
            "师傅/主管临时交办一件不在计划内的活",
            "原定工序被插队，需要先处理突发事项",
        ),
        advice="早到十分钟把当天主线工作先排好，留出缓冲；接到临时任务先记下来再答应时限。",
        caution="临时任务容易和原计划撞车，重要节点（收料、浇筑）提前和人打招呼。",
    ),
    "career.role_change": EventNarrative(
        scenarios=(
            "被调换到新的班组/工区或换带教师傅",
            "职责范围扩大或收缩的口头/书面通知",
            "实习内容与原定岗位明显不同",
        ),
        advice="主动找带教师傅聊一次接下来想什么方向，比等通知更有用。",
        caution="变动期别急着表态站队，先看清新职责的权责边界。",
    ),
    "career.job_offer": EventNarrative(
        scenarios=(
            "收到招聘方的面试/意向联系",
            "经熟人介绍得到一个岗位信息",
            "现单位释放转正/续约的积极信号",
        ),
        advice="把简历和证书材料提前备好放在手边，机会来了当天就能回应。",
        caution="口头承诺不算数，关键条件（薪资、到岗时间）要落到文字。",
    ),
    "career.conflict": EventNarrative(
        scenarios=(
            "与协作方在工序、责任划分上发生分歧",
            "因进度/质量问题被追问或与同事起争执",
            "群里或现场的言语摩擦升级",
        ),
        advice="对事不对人：把争议落到记录和图纸上，用影像/台账说话。",
        caution="气头上不回消息、不顶撞负责人，留十分钟再回应。",
    ),
    "career.noble_help": EventNarrative(
        scenarios=(
            "前辈主动点拨一个关键技术/流程问题",
            "有人替你解围、替你说话或引荐资源",
            "得到一份现成的模板/资料省去大量摸索",
        ),
        advice="之前卡住的问题（考证、资料、流程）主动请教一次，接住递过来的梯子。",
        caution="受人帮助记得及时回话致谢，关系是来往出来的。",
    ),
    # ------------------------------------------------ money
    "money.unplanned_expense": EventNarrative(
        scenarios=(
            "工具、劳保、交通、人情等突发开销",
            "垫付/补票/应急购置类支出",
            "社交应酬产生计划外花销",
        ),
        advice="当天上午就把可买可不买的东西放进「隔天再定」清单。",
        caution="留意「小钱漏财」模式，单笔不大但几笔叠加可观。",
    ),
    "money.income": EventNarrative(
        scenarios=(
            "报销、补贴、奖金等非固定收入到账",
            "旧账被归还或结算款下放",
            "一笔预期外的进账（含红包）",
        ),
        advice="到账先核对金额与名目，顺手把该存的转出去。",
        caution="到账延迟不等于黄了，先查流程再追问。",
    ),
    "money.large_purchase": EventNarrative(
        scenarios=(
            "电子产品、装备、课程等千元级消费",
            "为工作/生活添置大件",
        ),
        advice="看中后先晾 48 小时再下单，躲过冲动峰值。",
        caution="比价再出手；分期类注意总成本。",
    ),
    # ------------------------------------------------ relationship
    "relationship.romantic_encounter": EventNarrative(
        scenarios=(
            "在同事/同学/朋友介绍下认识一个有好感的异性",
            "与某位旧识重新热络起来，互动明显变多",
            "在公共场合被主动搭讪或有人对你表现出明显关注",
        ),
        advice="那天别宅着：答应邀约、把自己收拾利落，聊天时多问对方的事。",
        caution="心动归心动，私事（住址、财务、家庭矛盾）别急着掏。",
    ),
    "relationship.relationship_progress": EventNarrative(
        scenarios=(
            "与在意的对象有一次单独的、超过寒暄层面的相处",
            "彼此把关系往明确方向推进一步（表白/确定关系/重大约定）",
            "有伴侣的：一次走心的长谈，化解积累的小疙瘩",
        ),
        advice="想见的人就主动约，约具体的时间和地点，别停留在「改天」。",
        caution="推进是双向的，对方明显回避就收半步，别追问。",
    ),
    "relationship.rival_or_misunderstanding": EventNarrative(
        scenarios=(
            "因误会或传话导致与在意的人有小摩擦",
            "感情上的吃醋、猜疑或立场分歧",
            "冷战式的已读不回、刻意疏远",
        ),
        advice="情绪上头时不发长消息，约线下或电话十分钟讲清。",
        caution="别通过共同朋友传话，传一句走样三分。",
    ),
    # ------------------------------------------------ social
    "social.new_contact": EventNarrative(
        scenarios=(
            "新工友/新同事/新加入的同行",
            "聚会、培训、现场协作中自然结识",
            "线上加到同城或同好并聊开",
        ),
        advice="当天加个联系方式并发一句具体的话（而非「以后联系」）。",
        caution="新关系先观察分寸，金钱借贷类话题一律先挡。",
    ),
    "social.old_contact": EventNarrative(
        scenarios=(
            "久未联系的同学/老乡/旧同事主动来消息",
            "因某条动态或某件事勾起旧关系重新连线",
        ),
        advice="接住这个话头，问一句近况；旧关系往往带来信息差。",
        caution="久不联系的人突然涉及借钱、投资类话题要提高警惕。",
    ),
    "social.conflict": EventNarrative(
        scenarios=(
            "群聊观点分歧升级",
            "与熟人因琐事（借钱、帮忙失约）起不愉快",
        ),
        advice="争议话题线下说，群里只回事实不回情绪。",
        caution="分清「观点之争」与「利益之争」，前者不值得伤和气。",
    ),
    "social.gathering": EventNarrative(
        scenarios=(
            "饭局/聚餐/班组活动的邀请",
            "婚礼、满月酒、生日等人情场合",
        ),
        advice="答应一场就去一场，人到比礼到人缘长。",
        caution="酒桌场合守住健康与交通两条底线（不酒驾、早抽身）。",
    ),
    # ------------------------------------------------ study
    "study.study_session": EventNarrative(
        scenarios=(
            "考证/规范/软件操作的一段专注学习",
            "把白天现场遇到的问题下班搞懂",
        ),
        advice="把最难的内容放在精力最好的时段，25 分钟一段。",
        caution="别用「收藏资料」代替「学习」本身。",
    ),
    "study.goal_complete": EventNarrative(
        scenarios=("一个章节/一门课程/一项技能的阶段性收官",),
        advice="收尾后给自己做一次小测验，没实感的「学完」不算数。",
        caution="达成后别立刻松掉节奏，趁热定下一个目标。",
    ),
    # ------------------------------------------------ project / schedule / misc
    "project.new_project": EventNarrative(
        scenarios=(
            "新的楼栋/标段/阶段开工交底",
            "个人侧项目（作品、副业、学习项目）正式启动",
        ),
        advice="第一天就把目标、节点、风险写成一页纸。",
        caution="开局别贪多线程，先保主线不断。",
    ),
    "project.delay": EventNarrative(
        scenarios=(
            "天气/材料/验收等环节卡壳导致顺延",
            "上游未交付导致你这段被迫等待",
        ),
        advice="提前准备 Plan B 清单：等待期间能推进什么就先推进。",
        caution="延期的责任链留念痕（聊天记录/照片），不是甩锅是自保。",
    ),
    "project.milestone": EventNarrative(
        scenarios=("工程节点验收、阶段考核、作品发布等标志性完成",),
        advice="验收前把台账和影像证据按目录整理好。",
        caution="节点过后容易松劲，提前想好下一个节点。",
    ),
    "schedule.disruption": EventNarrative(
        scenarios=(
            "临检、通知变动、接送安排打乱当天节奏",
            "他人失约导致你的计划连锁调整",
        ),
        advice="把当天最重要的事放上午做，被打断的损失最小。",
        caution="被打断后先重建当天剩余计划，再处理插入事项。",
    ),
    "unexpected_event.major": EventNarrative(
        scenarios=(
            "现场安全/设备类的突发小状况",
            "家庭或个人生活里需要临时应对的事",
        ),
        advice="第一原则是人身安全，其余皆可补救。",
        caution="遇事先报、先记录，再处理；顺序别反。",
    ),
    "communication.message_volume_spike": EventNarrative(
        scenarios=(
            "工作群通知、布置任务集中轰炸",
            "某个事项引发多方同时联系你",
        ),
        advice="集中时段批量处理消息，重点事项单独置顶。",
        caution="量大队易漏：把「需要行动」的挑出来单列。",
    ),
    "habit.break": EventNarrative(
        scenarios=("锻炼/早睡/记账等既定习惯当天断档",),
        advice="把习惯和一个固定动作绑定（饭后、下工后），降低启动成本。",
        caution="断一天不是失败，断三天才是；别自责到放弃。",
    ),
    "travel.trip": EventNarrative(
        scenarios=(
            "出差、探亲、回家等跨城行程",
            "为办事（证件、材料、体检）专程跑一趟",
        ),
        advice="提前一天确认车次/天气/要带的东西。",
        caution="看好随身物品和重要证件；行程变更早告知等你的人。",
    ),
}

# 未知事件的兜底叙事（理论上 Ontology 外的类型走不到这里，双保险）
# 用词需避开对抗 Gate 的禁词（贵人/桃花/运势/可能/相关 等，见 DefinitionAttack）。
_GENERIC = EventNarrative(
    scenarios=("一件与「{label}」有关的可辨识事件",),
    advice="按平常心推进，留意与「{label}」有关的迹象。",
    caution="无特别提示。",
)


def get_narrative(event_type: str) -> EventNarrative:
    return NARRATIVES.get(event_type, _GENERIC)
