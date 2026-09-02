# 玄鉴 XuanMirror

> 个人智能未来预测、验证与自校准系统

**核心原则**：`Prediction → Freeze → Reality → Verify → Score → Diagnose → Learn → Predict Again`

---

## 这不是什么

不是一个「AI 算命聊天机器人」。

传统产品的工作方式是：`用户提问 → 排盘/起卦 → LLM 生成解释 → 结束`。

玄鉴的目标不是「解释得像大师」，而是建立一个可以长期运行、**主动生成预测、接受现实检验并持续校准**的系统。

系统的真正产品不是命盘，而是：

> **一个不断被现实检验的个人 Future Model。**

---

## 最高宪法（节选）

完整版见 [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md)，工程方案见 [`docs/工程方案_v1.0.md`](docs/%E5%B7%A5%E7%A8%8B%E6%96%B9%E6%A1%88_v1.0.md)。

| ID | 原则 |
|---|---|
| C-001 | **可证伪原则** — 无法失败的预测，不允许进入正式预测账本 |
| C-002 | **预测先于结果** — 正式预测必须在结果发生前生成、写入、冻结 |
| C-003 | **不允许事后改口** — 修订只能 `v1 → v2`，原版本永久存在 |
| C-004 | **全失败样本保留** — 命中/未命中/部分/无法验证/被拦截，全部永久保存 |
| C-005 | **概率而不是绝对断言** — 核心输出必须是概率 |
| C-006 | **不得假设术数具有科学预测效力** — 术数作为待验证信号进入系统 |
| C-007 | **现实优先** — 医疗/法律/财务/安全领域，现实证据 > 历史规律 > 术数解释 |

**硬性原则**：

> 未经验证的预测不是知识。
> 无法失败的预测不是预测。
> 发生以后才补出来的解释，不算预测能力。
> 如果 Null Model 比玄学模型更强，就必须承认玄学模型没有贡献。

---

## 当前状态：V1.0 达成（87 个测试通过）

本仓库交付的是**完整实现**，V1.0 十项验收标准（PRED-01…EXP-01）全部通过：

- ✅ 37 张数据库表（SQLModel / SQLite）
- ✅ **七个术式引擎全部接入**：八字(lunar-python) / 紫微(iztro-py) / 六爻(自研) / 梅花(自研) / 奇门(移植) / 掌纹(OpenCV) / 面相(OpenCV)
- ✅ 21 个 Agent（LLM 真实可用，qiyovo.com:3000）
- ✅ 14 种对抗性 Attack + 串联 Gate
- ✅ 评分体系 + 校准 + 可靠度矩阵 + Skill vs Null
- ✅ 学习闭环（归因 / Shadow / 规则统计 / 消融 / 可靠度回喂）
- ✅ Scheduler 每日自动闭环（23:30→23:55）
- ✅ Future Tree + Counterfactual
- ✅ Obsidian 导出 + 日报 / 周报 / 月报 / 审计
- ✅ 双盲实验（A/B/C 三组）+ Hidden Prediction
- ✅ 完整前端 8 页面 + ECharts

版本路线（方案第 66–75 节）：

| 版本 | 内容 | 状态 |
|---|---|---|
| V0.1 | 用户档案 / Calendar Core / 八字 / Reality / Future Scanner / Prediction Ledger / 人工验证 / Brier | ✅ |
| V0.2 | + 紫微 / Blind Agent / Null Model | ✅ |
| V0.3 | + 六爻 / 梅花 / Adversarial Gate | ✅ |
| V0.4 | + 奇门 / Prediction Budget / Hidden Prediction | ✅ |
| V0.5 | + Calibration / Skill Score / Reliability Matrix / Error Attribution | ✅ |
| V0.6 | + Obsidian Export / 日报周报 | ✅ |
| V0.7 | + Future Tree / Counterfactual | ✅ |
| V0.8 | + Palm CV / Face Landmark | ✅ |
| V0.9 | + Shadow Learning / Rule Registry / Ablation Testing | ✅ |
| V1.0 | 验收标准 PRED-01…EXP-01 | ✅ 达成 |

**已知限制**：qiyovo.com:3000 中转站对长 prompt（>1k tokens）响应慢（~50s），
术式 Agent 已通过 `_summarize_chart` 精简输入规避；掌纹/面相需提供本地照片才产出信号。

---

## 目录结构

```
xuanmirror/
├─ app/
│  ├─ api/             FastAPI 路由
│  ├─ core/            Calendar Core + 七个术式 Adapter
│  │  ├─ calendar/     ├─ ziwei/  ├─ bazi/  ├─ qimen/
│  │  ├─ liuyao/       ├─ meihua/ ├─ palm/  └─ face/
│  ├─ agents/          21 个 Agent（Blind Multi-Agent）
│  ├─ prediction/      候选 → 预算 → 冻结 → 账本
│  ├─ adversarial/     14 种 Attack + Gate
│  ├─ calibration/     Brier / LogLoss / Calibration / Sharpness
│  ├─ learning/        归因 / Shadow / Rule Registry / 提升
│  ├─ reality/         RealityState / Reality Event Ledger
│  ├─ providers/       LLM Adapter（reasoning / cheap / vision）
│  ├─ models/          SQLModel 数据表
│  ├─ schemas/         Pydantic 传输模型（Signal / Prediction / Outcome）
│  └─ services/        编排服务
├─ prompts/            Prompt 版本库
├─ rules/              Rule Registry（YAML）
├─ tests/golden/       deterministic engine golden cases
├─ frontend/           React + TS + Vite + Tailwind + ECharts
└─ reports/            日报 / 周报 / 月报 / 审计
```

---

## 快速开始

```bash
# 后端
pip install -e ".[engines,dev]"
cp .env.example .env
uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs

# 前端
cd frontend
npm install
npm run dev
```

---

## 安全边界

> 这是一个传统术数与个人预测实验平台，**不是经科学验证的预知系统**。

系统不得：以术数诊断疾病、预测死亡日期、替代医生/律师/财务专业人士、鼓励高风险下注、因面部特征推断敏感人格事实。

面部、掌纹、出生信息属于高敏感个人数据，遵循**本地优先**原则。

---

## 许可

私人实验项目。
