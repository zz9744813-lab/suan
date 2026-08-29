import { NavLink, Navigate, Route, Routes } from 'react-router-dom';

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
const NAV = [
  { to: '/future', label: '未来', hint: '今日预测与已冻结账本' },
  { to: '/verify', label: '验证', hint: '待验证收件箱' },
  { to: '/timeline', label: '时间线', hint: '历史成败全量展示' },
  { to: '/labs', label: '实验室', hint: '校准曲线与消融实验' },
  { to: '/charts', label: '命盘', hint: '术式引擎与历法快照' },
  { to: '/rules', label: '规则', hint: 'Rule Registry' },
  { to: '/models', label: '模型', hint: '可靠度矩阵与版本' },
  { to: '/settings', label: '设置', hint: 'Provider / 预算 / 隐私' },
];

export default function App() {
  return (
    <div className="flex h-full">
      {/* 侧边导航 */}
      <nav className="flex w-52 shrink-0 flex-col border-r border-ink-800 bg-ink-950">
        <div className="px-4 py-5">
          <div className="text-lg font-semibold tracking-wide text-slate-100">玄鉴</div>
          <div className="text-xs text-slate-600">XuanMirror</div>
        </div>

        <ul className="flex-1 space-y-0.5 px-2">
          {NAV.map((n) => (
            <li key={n.to}>
              <NavLink
                to={n.to}
                className={({ isActive }) =>
                  `block rounded px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? 'bg-ink-800 text-slate-100'
                      : 'text-slate-500 hover:bg-ink-900 hover:text-slate-300'
                  }`
                }
                title={n.hint}
              >
                {n.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="border-t border-ink-800 px-4 py-3 text-[11px] leading-relaxed text-slate-700">
          传统术数与个人预测实验平台，
          <br />
          不是经科学验证的预知系统。
        </div>
      </nav>

      {/* 内容区 */}
      <main className="flex-1 overflow-y-auto bg-ink-950">
        <div className="mx-auto max-w-6xl px-6 py-6">
          <Routes>
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
      </main>
    </div>
  );
}
