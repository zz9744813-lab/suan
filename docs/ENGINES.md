# 术式引擎接入指南（ENGINES.md）

> 对应工程方案第 53 节：不要粗暴 fork 后把整个项目揉成一个仓库。
> 建立 Adapter，输出统一 Schema。这样未来替换算法不会影响 Prediction Engine。

## 架构总览

```
                    ┌─────────────────────┐
                    │  Prediction Engine  │  ← 消费统一 Signal，不关心引擎实现
                    └──────────┬──────────┘
                               │ Signal（第 14 节统一 Schema）
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
  MetaphysicalAdapter     RealityAdapter         NullAgent
  （本目录目标）            （第 10 节）            （第 11 节）
        │
   ┌────┼────┬────┬────┬────┐
  Ziwei Bazi Qimen Liuyao Meihua Palm Face
```

每个术式 = 一个 Adapter（`app/core/<name>/adapter.py`），职责：

1. `available` — 底层引擎是否可用（诚实降级，绝不假装可用）
2. `compute_chart(query)` — 确定性排盘（第 54 节：相同输入必须相同输出）
3. `to_signals(query, chart)` — 排盘 → 统一 Signal（只允许 deterministic 规则映射）

**LLM 解释由对应的 `*Agent` 完成，不在此处**（第 6.1 节：程序负责排盘，LLM 不允许自己算命盘）。

## 当前状态

| 术式 | 参考仓库 | 计划版本 | 状态 |
|---|---|---|---|
| 八字 | 6tail/lunar-python | V0.1 | ✅ 已接入（`app/core/bazi/adapter.py`） |
| 紫微 | SylarLong/iztro | V0.2 | ⬜ 未接入（TS 库，需封装或 Node bridge） |
| 六爻 | Johnson-Jia/liuyao-divination | V0.3 | ⬜ 未接入 |
| 梅花 | handsomejustin/meihua-yi | V0.3 | ⬜ 未接入 |
| 奇门 | Maximilian-Winter/Qimen-Dunjia | V0.4 | ⬜ 未接入 |
| 掌纹 | yeonsumia/palmistry + MediaPipe | V0.8 | ⬜ 未接入 |
| 面相 | MediaPipe Face Landmark | V0.8 | ⬜ 未接入 |

未接入的 Adapter 返回 `degraded=True` 的 Signal。**Fusion 必须跳过 degraded 信号**，
而不是当作 0 —— 当作 0 会让「不可用」被误读为「强烈反对」。

## 接入一个新术式的步骤

以接入六爻为例：

### 1. 找到 Python 封装

```bash
pip install liuyao-divination   # 或手动移植/封装
```

### 2. 实现 Adapter

编辑 `app/core/liuyao/adapter.py`（骨架已生成）：

```python
class LiuyaoAdapter(MetaphysicalAdapter):
    source = SourceType.LIUYAO
    engine_name = "liuyao-divination"
    engine_version = "liuyao-0.1.0"

    @property
    def available(self) -> bool:
        try:
            import liuyao  # noqa: F401
            return True
        except ImportError:
            return False

    def compute_chart(self, query: AdapterQuery) -> dict[str, Any]:
        # 1. 用 CalendarCore 取历法（第 6.1 节：禁止自己算日期）
        # 2. 调用六爻库确定性排盘
        # 3. 返回 chart dict（含 input_hash，供 golden case 比对）
        raise NotImplementedError

    def to_signals(self, query: AdapterQuery, chart: dict[str, Any]) -> list[Signal]:
        # 传统规则映射（纳甲/六亲/世应 → direction/strength/confidence）
        # 每条规则先在 rules/ 下登记 rule_id（第 25 节）
        raise NotImplementedError
```

### 3. 登记规则（第 25 节）

在 `rules/<school>.yaml` 添加规则定义，给出唯一的 `rule_id`。

### 4. 写 Golden Cases（第 54 节）

在 `tests/golden/<school>/` 添加测试：

```python
# tests/golden/liuyao/test_deterministic.py
def test_same_input_same_chart():
    """输入完全相同 → 排盘必须完全相同。"""
    a = adapter.compute_chart(query1)
    b = adapter.compute_chart(query1)
    assert a == b
```

**LLM 解释可以变化，排盘不能变化。**

### 5. 更新本文件状态表 + `app/core/__init__.py` 确认已导入

## 降级契约

引擎不可用时的行为必须诚实：

```python
def signals(self, query: AdapterQuery) -> list[Signal]:
    if not self.available:
        return [self.degraded_signal(query, f"{self.engine_name} 引擎不可用")]
    ...
```

- `degraded=True` 的信号：Fusion 跳过（`app/agents/fusion.py` 已处理）
- `direction/strength/confidence` 全为 0，避免被当作「中性信号」

## 依赖

- `lunar-python`：八字/历法（已在 pyproject.toml 的 `engines` extra 中）
- 其余引擎**均为可选依赖**：缺失时对应 Adapter 进入 DEGRADED 状态，
  系统其余部分照常运行（第 6.1 节原则）。
