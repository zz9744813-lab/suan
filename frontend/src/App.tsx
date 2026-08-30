import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { api } from './api/client';
import { useAsync } from './lib/useAsync';
import Charts from './pages/Charts';
import Future from './pages/Future';
import Labs from './pages/Labs';
import Models from './pages/Models';
import Rules from './pages/Rules';
import Settings from './pages/Settings';
import Timeline from './pages/Timeline';
import Verify from './pages/Verify';

/**
 * 第 47 节 UI 信息架构：
 *   首页不应围绕「紫微 / 八字 / 奇门 / 六爻 / 梅花」，而应围绕 Future。
 */
const NAV_GROUPS: {
  label: string;
  items: { to: string; label: string; hint: string; icon: () => React.ReactElement }[];
}[] = [
  {
    label: '观未来',
    items: [
      { to: '/future', label: '未来', hint: '今日预测与已冻结账本', icon: IconFuture },
      { to: '/verify', label: '验证', hint: '待验证收件箱', icon: IconVerify },
      { to: '/timeline', label: '时间线', hint: '历史成败全量展示', icon: IconTimeline },
    ],
  },
  {
    label: '察自身',
    items: [
      { to: '/labs', label: '实验室', hint: '校准曲线与消融实验', icon: IconLabs },
      { to: '/charts', label: '命盘', hint: '术式引擎与历法快照', icon: IconCharts },
      { to: '/rules', label: '规则', hint: 'Rule Registry', icon: IconRules },
      { to: '/models', label: '模型', hint: '可靠度矩阵与版本', icon: IconModels },
    ],
  },
  {
    label: '系统',
    items: [
      { to: '/settings', label: '设置', hint: 'Provider / 预算 / 隐私', icon: IconSettings },
    ],
  },
];

function IconBase({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4 shrink-0"
    >
      {children}
    </svg>
  );
}

function IconFuture() {
  return (
    <IconBase>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      <circle cx="12" cy="12" r="3" />
    </IconBase>
  );
}
function IconVerify() {
  return (
    <IconBase>
      <path d="M9 12l2 2 4-4" />
      <circle cx="12" cy="12" r="9" />
    </IconBase>
  );
}
function IconTimeline() {
  return (
    <IconBase>
      <path d="M4 6h16M4 12h10M4 18h14" />
    </IconBase>
  );
}
function IconLabs() {
  return (
    <IconBase>
      <path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3" />
      <path d="M8 15h8" />
    </IconBase>
  );
}
function IconCharts() {
  return (
    <IconBase>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a9 9 0 0 1 0 18M12 8v4l3 2" />
    </IconBase>
  );
}
function IconRules() {
  return (
    <IconBase>
      <path d="M6 3h9l4 4v14H6z" />
      <path d="M15 3v4h4M9 12h6M9 16h4" />
    </IconBase>
  );
}
function IconModels() {
  return (
    <IconBase>
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </IconBase>
  );
}
function IconSettings() {
  return (
    <IconBase>
      <circle cx="12" cy="12" r="3" />
      <path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.7a7 7 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2 1.2l.4 2.7h4l.4-2.7a7 7 0 0 0 2-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z" />
    </IconBase>
  );
}

/** 后端离线时主内容区顶部的醒目横幅（可重试） */
function OfflineBanner() {
  const health = useAsync(() => api.health(), []);
  if (health.loading || !health.error) return null;
  return (
    <div className="mb-4 flex items-center gap-3 rounded-xl border border-cinnabar-500/30 bg-cinnabar-500/[0.07] px-4 py-2.5">
      <span className="h-2 w-2 shrink-0 rounded-full bg-cinnabar-400" />
      <div className="flex-1 text-xs text-slate-300">
        后端服务离线，页面数据不可用。请用桌面快捷方式或
        <span className="mx-1 font-mono text-slate-400">uvicorn app.main:app --port 8765</span>
        启动后端。
      </div>
      <button
        onClick={() => health.reload()}
        className="btn-press shrink-0 rounded-md border border-cinnabar-500/40 px-2.5 py-1 text-xs text-cinnabar-400 hover:bg-cinnabar-500/10"
      >
        重试连接
      </button>
    </div>
  );
}

/** 侧边栏底部的后端在线状态 */
function BackendStatus() {
  const health = useAsync(() => api.health(), []);
  const online = !health.error && health.data?.status != null;
  const engineOk = health.data
    ? Object.values(health.data.engines).filter((e) => e.available).length
    : 0;
  const engineTotal = health.data ? Object.keys(health.data.engines).length : 7;

  return (
    <div className="border-t border-ink-800 px-4 py-3">
      <div className="flex items-center gap-2 text-[11px]">
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            health.loading
              ? 'bg-slate-500'
              : online
                ? 'status-dot bg-jade-400'
                : 'bg-cinnabar-400'
          }`}
        />
        <span className={online ? 'text-slate-400' : 'text-slate-600'}>
          {health.loading ? '连接中…' : online ? '后端在线' : '后端离线'}
        </span>
        {online && (
          <span className="ml-auto tabular text-slate-600">
            引擎 {engineOk}/{engineTotal}
          </span>
        )}
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-slate-700">
        传统术数与个人预测实验平台，
        <br />
        不是经科学验证的预知系统。
      </p>
    </div>
  );
}

export default function App() {
  const location = useLocation();

  return (
    <div className="flex h-full">
      {/* 侧边导航 */}
      <nav className="relative flex w-56 shrink-0 flex-col border-r border-ink-800 bg-ink-950">
        {/* 顶部鎏金光晕 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(60%_100%_at_50%_0%,rgba(217,185,106,0.08),transparent)]"
        />

        <div className="relative flex items-center gap-3 px-5 py-6">
          {/* 印章式 Logo */}
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-gilt-500/30 bg-gilt-500/10 text-lg font-bold text-gilt-300">
            玄
          </div>
          <div>
            <div className="text-base font-semibold tracking-[0.2em] text-slate-100">玄鉴</div>
            <div className="text-[10px] tracking-widest text-slate-600">XUANMIRROR</div>
          </div>
        </div>

        <div className="relative flex-1 space-y-4 overflow-y-auto px-3">
          {NAV_GROUPS.map((g) => (
            <div key={g.label}>
              <div className="mb-1 px-3 text-[10px] font-medium tracking-[0.25em] text-slate-700">
                {g.label}
              </div>
              <ul className="space-y-0.5">
                {g.items.map((n) => (
                  <li key={n.to}>
                    <NavLink
                      to={n.to}
                      className={({ isActive }) =>
                        `group relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition-all duration-200 ${
                          isActive
                            ? 'bg-white/[0.06] font-medium text-slate-100'
                            : 'text-slate-500 hover:bg-white/[0.03] hover:text-slate-300'
                        }`
                      }
                      title={n.hint}
                    >
                      {({ isActive }) => (
                        <>
                          {/* 激活时左侧鎏金指示条 */}
                          <span
                            className={`absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-gilt-400 transition-all duration-200 ${
                              isActive ? 'opacity-100' : 'opacity-0'
                            }`}
                          />
                          <span
                            className={`transition-colors ${isActive ? 'text-gilt-400' : 'text-slate-600 group-hover:text-slate-400'}`}
                          >
                            <n.icon />
                          </span>
                          <span className="flex-1">{n.label}</span>
                        </>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <BackendStatus />
      </nav>

      {/* 内容区 */}
      <main className="relative flex-1 overflow-y-auto bg-ink-950">
        {/* 背景氛围光 */}
        <div
          aria-hidden
          className="pointer-events-none fixed inset-y-0 right-0 left-56 bg-[radial-gradient(50%_35%_at_70%_0%,rgba(217,185,106,0.05),transparent),radial-gradient(40%_30%_at_20%_100%,rgba(56,130,246,0.04),transparent)]"
        />
        <div className="relative mx-auto max-w-6xl px-6 py-6">
          <OfflineBanner />
          {/* 路由切换时的入场动效 */}
          <div key={location.pathname} className="animate-fade-up space-y-5">
            <Routes location={location}>
              <Route path="/" element={<Navigate to="/future" replace />} />
              <Route path="/future" element={<Future />} />
              <Route path="/verify" element={<Verify />} />
              <Route path="/timeline" element={<Timeline />} />
              <Route path="/labs" element={<Labs />} />
              <Route path="/charts" element={<Charts />} />
              <Route path="/rules" element={<Rules />} />
              <Route path="/models" element={<Models />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </div>
        </div>
      </main>
    </div>
  );
}
