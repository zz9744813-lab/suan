/**
 * RailNav — leftmost 56px dark vertical nav.
 *
 * Renders:
 *   1. Brand badge (top)
 *   2. Core nav group (Dashboard, Projects, Tasks, Worker)
 *   3. Sub-divider
 *   4. Learning group (Prompts, Models, Study)
 *   5. Recover button (only when project library is fully hidden)
 *   6. Worker state dot at the bottom
 *
 * The 8 routes match the plan section 1.2 ("Rail 导航"), with the
 * Phase-2 deferred items (writing / memory / export / settings) not
 * yet rendered.
 */
import { NavLink } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { useWorkerStore } from "../../stores/workerStore";
import { useLayoutStore } from "../../stores/layoutStore";
import { stateColor } from "../../lib/stateColor";
import "./RailNav.css";

type Item = { to: string; label: string; icon: string };

const CORE_ITEMS: Item[] = [
  { to: "/dashboard", label: "工作台", icon: "◧" },
  { to: "/projects",  label: "项目",   icon: "≡" },
  { to: "/tasks",     label: "任务",   icon: "▤" },
  { to: "/worker",    label: "Worker", icon: "▶" },
];

const LEARN_ITEMS: Item[] = [
  { to: "/prompts",    label: "Prompt",   icon: "✎" },
  { to: "/prompts-matrix", label: "Prompt矩阵", icon: "▦" },
  { to: "/models",     label: "模型",     icon: "◈" },
  { to: "/model-observability", label: "可观测性", icon: "◉" },
  { to: "/audit-logs", label: "审计日志", icon: "⚲" },
  { to: "/study",      label: "拆书",     icon: "☷" },
  { to: "/behavior",   label: "行为模式", icon: "✺" },
  { to: "/graphs",     label: "图谱",     icon: "◉" },
  { to: "/discussion", label: "讨论室",   icon: "☕" },
  { to: "/memory",     label: "记忆库",   icon: "❖" },
  // P6 P5: 评论区驱动的模拟读者 Agent 评审系统 (F:\07_P6 spec §7)
  { to: "/reviews",    label: "评论评审", icon: "✦" },
  // NF2: 读者Agent + 审计
  { to: "/reader-agents", label: "读者", icon: "📖" },
  { to: "/audit",      label: "审计",   icon: "🔍" },
];

export function RailNav() {
  // R17: theme switch (light/dark) is owned by the layout store
  // and persisted to localStorage. The button here sits where the
  // old "recover project nav" affordance used to live.
  const theme = useLayoutStore((s) => s.theme);
  const setTheme = useLayoutStore((s) => s.setTheme);

  // Touch the project store so the projectNav inside this rail (well,
  // the sibling project library) stays in sync. Worker state is what
  // drives the bottom status dot.
  useProjectStore((s) => s.projects);
  const workerState = useWorkerStore((s) => s.status?.state ?? "idle");

  return (
    <nav className="rail">
      <div className="rail-brand" title="NovelForge 2.0">NF</div>

      <button
        className="rail-theme-toggle"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        title={theme === "dark" ? "切换到日间模式" : "切换到夜间模式"}
        aria-label={theme === "dark" ? "切换到日间模式" : "切换到夜间模式"}
      >
        {theme === "dark" ? "☀" : "☾"}
      </button>

      <div className="rail-nav-scroll">
        <RailGroup items={CORE_ITEMS} />

        <div className="rail-divider" />

        <RailGroup items={LEARN_ITEMS} />
      </div>

      <div
        className={`rail-dot rail-dot-${stateColor(workerState)}`}
        title={`Worker: ${workerState}`}
      >
        <span className="rail-dot-tooltip">Worker: {workerState}</span>
      </div>
    </nav>
  );
}

function RailGroup({ items }: { items: Item[] }) {
  return (
    <>
      {items.map((it) => <RailItem key={it.to} {...it} />)}
    </>
  );
}

function RailItem({ to, label, icon }: Item) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) => `rail-item ${isActive ? "active" : ""}`}
      title={label}
    >
      <span className="rail-item-icon">{icon}</span>
      <span className="rail-item-label">{label}</span>
    </NavLink>
  );
}
