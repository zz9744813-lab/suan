import { useState } from 'react';

import { api, type LLMTestResult, type LLMTierConfig } from '../api/client';
import {
  Badge,
  Card,
  ErrorBox,
  Field,
  GhostButton,
  Loading,
  PageHeader,
  PrimaryButton,
  TextInput,
  inputCls,
} from '../components/ui';
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

const TIER_META: Record<string, { label: string; desc: string }> = {
  reasoning: { label: 'Reasoning · 强推理', desc: 'Fusion 融合 / 对抗审查 / 月度审计' },
  cheap: { label: 'Cheap · 轻量', desc: 'Signal 格式化 / Outcome 解析' },
  vision: { label: 'Vision · 视觉', desc: '掌纹 / 面相（默认关闭，本地优先）' },
};

/** 单个分层的配置表单 */
function TierForm({
  tier,
  config,
  onSaved,
}: {
  tier: string;
  config: LLMTierConfig | undefined;
  onSaved: () => void;
}) {
  const [baseUrl, setBaseUrl] = useState(config?.base_url ?? '');
  const [model, setModel] = useState(config?.model ?? '');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const dirty =
    baseUrl !== (config?.base_url ?? '') || model !== (config?.model ?? '') || apiKey !== '';

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await api.saveLLMConfig(tier, {
        base_url: baseUrl,
        model,
        ...(apiKey ? { api_key: apiKey } : {}),
      });
      setApiKey('');
      setMsg({ text: '已保存，立即生效（无需重启）', ok: true });
      onSaved();
    } catch (e) {
      setMsg({ text: e instanceof Error ? e.message : String(e), ok: false });
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setMsg(null);
    try {
      const r: LLMTestResult = await api.testLLMConfig(tier, {
        base_url: baseUrl,
        model,
        ...(apiKey ? { api_key: apiKey } : {}),
      });
      if (r.ok) {
        setMsg({
          text: `连接成功 · ${r.model} · ${((r.duration_ms ?? 0) / 1000).toFixed(1)}s${r.sample ? ` · 回复「${r.sample}」` : ''}`,
          ok: true,
        });
      } else {
        setMsg({ text: `连接失败：${r.error ?? '未知错误'}`, ok: false });
      }
    } catch (e) {
      setMsg({ text: e instanceof Error ? e.message : String(e), ok: false });
    } finally {
      setTesting(false);
    }
  };

  const meta = TIER_META[tier] ?? { label: tier, desc: '' };

  return (
    <div className="rounded-xl border border-white/[0.06] bg-ink-950/40 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-slate-200">{meta.label}</span>
        <Badge tone={config?.configured ? 'good' : 'default'}>
          {config?.configured ? '已配置' : '未配置'}
        </Badge>
        {(config?.overridden_fields.length ?? 0) > 0 && (
          <Badge tone="gilt">页面配置覆盖 .env</Badge>
        )}
        <span className="ml-auto text-[11px] text-slate-600">{meta.desc}</span>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Base URL">
          <TextInput
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://your-endpoint/v1"
          />
        </Field>
        <Field label="模型">
          <TextInput
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="deepseek-v4-flash"
          />
        </Field>
        <div className="md:col-span-2">
          <Field
            label="API Key"
            hint={
              config?.has_api_key
                ? `当前 ${config.api_key_masked} · 留空表示不修改；key 只保存在后端，不下发`
                : '只保存在后端（.env 或 data/llm_config.json），不下发前端、不落日志'
            }
          >
            <TextInput
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={config?.has_api_key ? '留空保持不变' : 'sk-…'}
              autoComplete="off"
            />
          </Field>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <PrimaryButton onClick={save} busy={saving} disabled={!dirty || testing}>
          保存
        </PrimaryButton>
        <GhostButton onClick={test} disabled={testing || saving}>
          {testing ? '测试中（中转站可能需 1-3 分钟）…' : '测试连接'}
        </GhostButton>
        {msg && (
          <span
            className={`animate-fade-in text-xs ${msg.ok ? 'text-jade-400' : 'text-cinnabar-400'}`}
          >
            {msg.text}
          </span>
        )}
      </div>
    </div>
  );
}

export default function Settings() {
  const meta = useAsync(() => api.meta(), []);
  const users = useAsync(() => api.listUsers(), []);
  const llm = useAsync(() => api.llmConfig(), []);

  const [userKey, setUserKey] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [birthTime, setBirthTime] = useState('00:00');
  const [timeKnown, setTimeKnown] = useState(false);
  const [gender, setGender] = useState('unknown');
  const [birthPlace, setBirthPlace] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  // 编辑已有档案：选中用户后回填
  const [editingId, setEditingId] = useState<number | null>(null);
  const [profile, setProfile] = useState<{
    solar_birth_date: string;
    solar_birth_time: string;
    birth_time_known: boolean;
    gender: string;
    birth_place: string;
  } | null>(null);

  const versions = (meta.data?.versions ?? {}) as Record<string, string>;
  const notice = typeof meta.data?.notice === 'string' ? meta.data.notice : '';

  const loadProfile = async (id: number) => {
    setMsg(null);
    try {
      const p = await api.profile(id);
      setEditingId(id);
      setProfile({
        solar_birth_date: p.solar_birth_date,
        solar_birth_time: p.solar_birth_time,
        birth_time_known: p.birth_time_known,
        gender: p.gender,
        birth_place: p.birth_place,
      });
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const createUser = async () => {
    setMsg(null);
    try {
      const birth = birthDate
        ? {
            solar_birth_date: birthDate,
            solar_birth_time: birthTime,
            birth_time_known: timeKnown,
            gender,
            birth_place: birthPlace,
          }
        : undefined;
      const r = await api.createUser(userKey, birth);
      setMsg(`已创建用户 ${r.user_key}（id=${r.user_id}）`);
      setUserKey('');
      setBirthDate('');
      setBirthTime('00:00');
      setTimeKnown(false);
      setGender('unknown');
      setBirthPlace('');
      users.reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const saveProfile = async () => {
    if (editingId == null || !profile) return;
    setMsg(null);
    try {
      await api.updateProfile(editingId, profile);
      setMsg(`已更新用户 id=${editingId} 的出生档案，命盘将按新信息重排`);
      setProfile(null);
      setEditingId(null);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="设置"
        desc="LLM Provider、预测预算、隐私开关与实验模式。Provider 改动保存后立即生效。"
      />

      {notice && (
        <div className="animate-fade-in rounded-xl border border-amber-500/30 bg-amber-500/[0.08] px-4 py-3 text-sm text-amber-300">
          {notice}
        </div>
      )}

      {/* LLM Provider 配置：第 41 / 42 节 */}
      <Card
        title="LLM Provider"
        subtitle="第 41 节：OpenAI 兼容端点即可接入。页面配置保存在后端 data/llm_config.json，优先级高于 .env"
      >
        {llm.loading && <Loading />}
        {llm.error && <ErrorBox message={llm.error} />}
        {!llm.loading && !llm.error && (
          <div className="space-y-3">
            {['reasoning', 'cheap', 'vision'].map((tier) => (
              <TierForm
                key={`${tier}-${llm.data?.tiers[tier]?.base_url}-${llm.data?.tiers[tier]?.model}`}
                tier={tier}
                config={llm.data?.tiers[tier]}
                onSaved={llm.reload}
              />
            ))}
          </div>
        )}
      </Card>

      <Card title="系统版本" subtitle="第 79 节：任何修改都需要版本号，更新后性能下降会触发回归告警">
        {meta.loading && <Loading />}
        {meta.error && <ErrorBox message={meta.error} />}
        <div className="grid gap-2 text-xs md:grid-cols-5">
          {Object.entries(versions).map(([k, v]) => (
            <div key={k} className="rounded-xl bg-ink-950/60 px-3 py-2.5">
              <div className="text-slate-600">{k}</div>
              <div className="mt-0.5 font-mono text-slate-300">{String(v)}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="模型分层" subtitle="第 42 节：不是所有任务都需要最贵的模型">
        <table className="w-full text-xs">
          <thead className="text-slate-600">
            <tr className="border-b border-white/[0.06]">
              <th className="py-2 text-left font-medium">任务</th>
              <th className="py-2 text-left font-medium">层级</th>
              <th className="py-2 text-left font-medium">依据</th>
            </tr>
          </thead>
          <tbody className="text-slate-400">
            {TIERS.map((t) => (
              <tr key={t.task} className="row-hover border-b border-white/[0.04]">
                <td className="py-2">{t.task}</td>
                <td className="py-2">
                  <Badge tone={t.tier.includes('程序') ? 'info' : 'default'}>{t.tier}</Badge>
                </td>
                <td className="py-2 text-slate-600">{t.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="预测预算" subtitle="第 4 节：强制下注制度，禁止撒网式算准">
          <table className="w-full text-xs">
            <tbody className="text-slate-400">
              {BUDGET.map(([k, v]) => (
                <tr key={k} className="border-b border-white/[0.04]">
                  <td className="py-2">{k}</td>
                  <td className="py-2 text-right tabular text-slate-200">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[11px] leading-relaxed text-slate-600">
            只有 Information Value 最高的预测才能获得额度。候选命中不计入正式评分
            （第 20.6 节 MultipleTestingAttack）。
          </p>
        </Card>

        <Card title="隐私与实验模式" subtitle="第 64 / 34 / 35 节">
          <ul className="space-y-3 text-xs leading-relaxed text-slate-400">
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
              <span>只允许后端保存，不落日志、不下发前端（第 41 节）。</span>
            </li>
          </ul>
        </Card>
      </div>

      <Card title="用户档案" subtitle="出生信息属高敏感个人数据（第 64 节），仅存本地。出生时间用于八字时柱与紫微命宫排盘">
        {users.loading && <Loading />}
        {users.data && (
          <div className="mb-4 flex flex-wrap gap-2">
            {users.data.items.map((u) => (
              <button
                key={u.id}
                onClick={() => loadProfile(u.id)}
                className={`btn-press rounded-md border px-2.5 py-1 text-xs transition-colors ${
                  editingId === u.id
                    ? 'border-gilt-500/50 bg-gilt-500/10 text-gilt-300'
                    : 'border-ink-700 text-slate-400 hover:border-ink-600 hover:text-slate-200'
                }`}
              >
                {u.user_key} (id={u.id})
              </button>
            ))}
            {users.data.items.length === 0 && (
              <span className="text-xs text-slate-600">暂无用户</span>
            )}
          </div>
        )}

        {/* 编辑已有档案 */}
        {profile && (
          <div className="mb-4 animate-fade-up rounded-xl border border-gilt-500/30 bg-gilt-500/[0.06] p-4">
            <div className="mb-3 flex items-center gap-2">
              <span className="text-sm font-medium text-gilt-300">
                编辑出生档案（id={editingId}）
              </span>
              <Badge tone="gilt">命盘将按此重排</Badge>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="出生日期">
                <TextInput
                  type="date"
                  value={profile.solar_birth_date}
                  onChange={(e) =>
                    setProfile({ ...profile, solar_birth_date: e.target.value })
                  }
                />
              </Field>
              <Field label="出生时间（时辰）">
                <TextInput
                  type="time"
                  value={profile.solar_birth_time}
                  onChange={(e) =>
                    setProfile({ ...profile, solar_birth_time: e.target.value })
                  }
                />
              </Field>
              <Field label="性别">
                <select
                  value={profile.gender}
                  onChange={(e) => setProfile({ ...profile, gender: e.target.value })}
                  className={inputCls}
                >
                  <option value="unknown">未设置</option>
                  <option value="male">男</option>
                  <option value="female">女</option>
                </select>
              </Field>
              <Field label="出生地">
                <TextInput
                  value={profile.birth_place}
                  onChange={(e) =>
                    setProfile({ ...profile, birth_place: e.target.value })
                  }
                  placeholder="如 北京（可选）"
                />
              </Field>
              <Field label="出生时间是否确定">
                <select
                  value={profile.birth_time_known ? 'yes' : 'no'}
                  onChange={(e) =>
                    setProfile({ ...profile, birth_time_known: e.target.value === 'yes' })
                  }
                  className={inputCls}
                >
                  <option value="no">不确定（时柱存疑）</option>
                  <option value="yes">确定</option>
                </select>
              </Field>
            </div>
            <div className="mt-3 flex gap-2">
              <PrimaryButton onClick={saveProfile}>保存档案</PrimaryButton>
              <GhostButton onClick={() => { setProfile(null); setEditingId(null); }}>
                取消
              </GhostButton>
            </div>
          </div>
        )}

        {/* 新建用户 */}
        <div className="flex flex-wrap items-end gap-3">
          <Field label="user_key（姓名）">
            <div className="w-36">
              <TextInput
                value={userKey}
                onChange={(e) => setUserKey(e.target.value)}
                placeholder="姓名"
              />
            </div>
          </Field>
          <Field label="出生日期">
            <div className="w-40">
              <TextInput
                type="date"
                value={birthDate}
                onChange={(e) => setBirthDate(e.target.value)}
              />
            </div>
          </Field>
          <Field label="出生时间">
            <div className="w-28">
              <TextInput
                type="time"
                value={birthTime}
                onChange={(e) => setBirthTime(e.target.value)}
              />
            </div>
          </Field>
          <Field label="性别">
            <div className="w-24">
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                className={inputCls}
              >
                <option value="unknown">未知</option>
                <option value="male">男</option>
                <option value="female">女</option>
              </select>
            </div>
          </Field>
          <Field label="出生地（可选）">
            <div className="w-36">
              <TextInput
                value={birthPlace}
                onChange={(e) => setBirthPlace(e.target.value)}
                placeholder="如 北京"
              />
            </div>
          </Field>
          <Field label="出生时间确定">
            <div className="w-28">
              <select
                value={timeKnown ? 'yes' : 'no'}
                onChange={(e) => setTimeKnown(e.target.value === 'yes')}
                className={inputCls}
              >
                <option value="no">不确定</option>
                <option value="yes">确定</option>
              </select>
            </div>
          </Field>
          <PrimaryButton onClick={createUser} disabled={!userKey} className="mb-0.5">
            创建
          </PrimaryButton>
        </div>
        {msg && <div className="animate-fade-in mt-3 text-xs text-sky-400">{msg}</div>}
      </Card>
    </div>
  );
}
