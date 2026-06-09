/**
 * RailNav — leftmost 56px dark vertical nav.
 *
 * M1: 收束为总编工作台的一级信息架构：
 * 首页 / 创作 / 研读 / 反馈 / 知识 / 治理。
 * 旧业务页不删除，改由各域工作台下钻进入。
 */
import { NavLink, useLocation } from "react-router-dom";
import { useProjectStore } from "../../stores/projectStore";
import { useWorkerStore } from "../../stores/workerStore";
import { useLayoutStore } from "../../stores/layoutStore";
import { WORKBENCH_DOMAINS } from "../../lib/domainMap";
import { stateColor } from "../../lib/stateColor";
import "./RailNav.css";

type Item = { to: string; label: string; icon: string; end?: boolean; legacyPrefixes?: string[] };

const legacyRoutePrefixes: Record<string, string[]> = {
  writing: ["/projects", "/tasks", "/worker"],
  study: ["/study", "/graphs", "/graph", "/behavior"],
  feedback: ["/reviews", "/discussion", "/reader-agents"],
  memory: ["/memory", "/memory-shelf"],
  governance: ["/models", "/prompts", "/prompts-matrix", "/model-observability", "/audit"],
};

const NAV_ITEMS: Item[] = [
  { to: "/dashboard", label: "首页", icon: "◧", end: true },
  ...WORKBENCH_DOMAINS.map((domain) => ({
    to: domain.path,
    label: domain.shortLabel,
    icon: domain.navIcon,
    legacyPrefixes: legacyRoutePrefixes[domain.key],
  })),
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
        <RailGroup items={NAV_ITEMS} />
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

function RailItem({ to, label, icon, end, legacyPrefixes }: Item) {
  const location = useLocation();
  const legacyActive = legacyPrefixes?.some((prefix) => location.pathname.startsWith(prefix));
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => `rail-item ${isActive || legacyActive ? "active" : ""}`}
      title={label}
    >
      <span className="rail-item-icon">{icon}</span>
      <span className="rail-item-label">{label}</span>
    </NavLink>
  );
}
