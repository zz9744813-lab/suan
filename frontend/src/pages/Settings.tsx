import { useState } from 'react';

import { api } from '../api/client';
import { Badge, Card, ErrorBox, Loading } from '../components/ui';
import { useAsync } from '../lib/useAsync';

/**
 * 第 41 节 LLM Provider 架构
 * 第 42 节 模型分层
 * 第 4 节 Prediction Budget
 * 第 34 节 双盲实验模式
 * 第 35 节 Hidden Prediction Mode
 * 第 64 节 隐私
 */

const TIERS = [
  { task: '规则计算（排盘）', tier: '程序，无 LLM', note: '第 6.1 节：LLM 不允许自己排盘' },
  { task: 'Signal 格式化', tier: 'cheap', note: '第 42 节' },
  { task: '结果解析 Outcome', tier: 'cheap', note: '第 42 节' },
  { task: '术式解释 Specialist', tier: 'reasoning（中高）', note: '第 42 节' },
  { task: 'Fusion 融合', tier: 'reasoning（强推理）', note: '第 42 节' },
  { task: '对抗性审查', tier: 'reasoning（独立强推理）', note: '第 20 节核心基础设施' },
  { task: '月度审计', tier: 'reasoning（强推理）', note: '第 31 节' },
];

const BUDGET = [
  ['明日强预测', 5],
  ['明日观察预测', 5],
  ['7 天预测', 5],
  ['30 天预测', 5],
  ['90 天预测', 3],
] as const;

export default function Settings() {
  const meta = useAsync(() => api.meta(), []);
  const users = useAsync(() => api.listUsers(), []);

  const [userKey, setUserKey] = useState('');
  const [birth, setBirth] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  const versions = (meta.data?.versions ?? {}) as Record<string, string>;
  const notice = typeof meta.data?.notice === 'string' ? meta.data.notice : '';

  const createUser = async () => {
    setMsg(null);
    try {
      const r = await api.createUser(
        userKey,
        birth ? { solar_birth_date: birth, birth_time_known: false } : undefined,
      );
      setMsg(`已创建用户 ${r.user_key}（id=${r.user_id}）`);
      setUserKey('');
      setBirth('');
      users.reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">设置</h1>
        <p className="mt-1 text-xs text-slate-500">
          Provider 分层、预测预算、隐私开关与实验模式。实际值来自后端 .env。
        </p>
      </header>

      {notice && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          {notice}
        </div>
      )}

      <Card title="系统版本" subtitle="第 79 节：任何修改都需要版本号，更新后性能下降会触发回归告警">
        {meta.loading && <Loading />}
        {meta.error && <ErrorBox message={meta.error} />}
        <div className="grid gap-2 text-xs md:grid-cols-5">
          {Object.entries(versions).map(([k, v]) => (
            <div key={k} className="rounded bg-ink-900 px-3 py-2">
              <div className="text-slate-600">{k}</div>
              <div className="mt-0.5 font-mono text-slate-300">{String(v)}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="模型分层" subtitle="第 42 节：不是所有任务都需要最贵的模型">
        <table className="w-full text-xs">
          <thead className="text-slate-600">
            <tr className="border-b border-ink-800">
              <th className="py-1.5 text-left">任务</th>
              <th className="py-1.5 text-left">层级</th>
              <th className="py-1.5 text-left">依据</th>
            </tr>
          </thead>
          <tbody className="text-slate-400">
            {TIERS.map((t) => (
              <tr key={t.task} className="border-b border-ink-800/50">
                <td className="py-1.5">{t.task}</td>
                <td className="py-1.5">
                  <Badge tone={t.tier.includes('程序') ? 'info' : 'default'}>{t.tier}</Badge>
                </td>
                <td className="py-1.5 text-slate-600">{t.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        <Card
          title="预测预算"
          subtitle="第 4 节：强制下注制度，禁止撒网式算准"
        >
          <table className="w-full text-xs">
            <tbody className="text-slate-400">
              {BUDGET.map(([k, v]) => (
                <tr key={k} className="border-b border-ink-800/50">
                  <td className="py-1.5">{k}</td>
                  <td className="py-1.5 text-right tabular text-slate-200">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-slate-600">
            只有 Information Value 最高的预测才能获得额度。候选命中不计入正式评分
            （第 20.6 节 MultipleTestingAttack）。
          </p>
        </Card>

        <Card title="隐私与实验模式" subtitle="第 64 / 34 / 35 节">
          <ul className="space-y-2 text-xs text-slate-400">
            <li className="flex items-start gap-2">
              <Badge tone="info">第 64 节</Badge>
              <span>面部、掌纹、出生信息属高敏感数据。原始照片本地保存，上传前裁剪，可关闭云 Vision。</span>
            </li>
            <li className="flex items-start gap-2">
              <Badge tone="info">第 35 节</Badge>
              <span>Hidden Prediction：预测冻结后对用户不可见，窗口结束后先问实情再公开，防止自我实现。</span>
            </li>
            <li className="flex items-start gap-2">
              <Badge tone="info">第 34 节</Badge>
              <span>双盲对照：Reality+Null / 纯术数 / 融合 三组在互不知情下预测，长期比较。</span>
            </li>
            <li className="flex items-start gap-2">
              <Badge tone="warn">API Key</Badge>
              <span>只允许后端保存，不落日志、不入库、不下发前端（第 41 节）。</span>
            </li>
          </ul>
        </Card>
      </div>

      <Card title="用户档案" subtitle="出生信息属高敏感个人数据（第 64 节）">
        {users.loading && <Loading />}
        {users.data && (
          <div className="mb-3 flex flex-wrap gap-2">
            {users.data.items.map((u) => (
              <Badge key={u.id}>
                {u.user_key} (id={u.id})
              </Badge>
            ))}
            {users.data.items.length === 0 && (
              <span className="text-xs text-slate-600">暂无用户</span>
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <input
            value={userKey}
            onChange={(e) => setUserKey(e.target.value)}
            placeholder="user_key"
            className="rounded border border-ink-700 bg-ink-900 px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
          />
          <input
            type="date"
            value={birth}
            onChange={(e) => setBirth(e.target.value)}
            className="rounded border border-ink-700 bg-ink-900 px-3 py-1.5 text-xs text-slate-200 focus:border-slate-600 focus:outline-none"
          />
          <button
            onClick={createUser}
            disabled={!userKey}
            className="rounded bg-slate-200 px-3 py-1.5 text-xs font-medium text-ink-950 disabled:opacity-40"
          >
            创建
          </button>
        </div>
        {msg && <div className="mt-2 text-xs text-sky-400">{msg}</div>}
      </Card>
    </div>
  );
}