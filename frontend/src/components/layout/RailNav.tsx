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
  { to: "/models",     label: "模型",     icon: "◈" },
  { to: "/study",      label: "拆书",     icon: "☷" },
  { to: "/discussion", label: "讨论室",   icon: "☕" },
  { to: "/memory",     label: "知识库",   icon: "❖" },
];

export function RailNav() {
  const projectNavMode = useLayoutStore((s) => s.projectNavMode);
  const setProjectNavMode = useLayoutStore((s) => s.setProjectNavMode);

  // Touch the project store so the projectNav inside this rail (well,
  // the sibling project library) stays in sync. Worker state is what
  // drives the bottom status dot.
  useProjectStore((s) => s.projects);
  const workerState = useWorkerStore((s) => s.status?.state ?? "idle");

  return (
    <nav className="rail">
      <div className="rail-brand" title="NovelForge 2.0">NF</div>

      <RailGroup items={CORE_ITEMS} />

      <div className="rail-divider" />

      <RailGroup items={LEARN_ITEMS} />

      <div className="rail-spacer" />

      {projectNavMode === "hidden" && (
        <button
          className="rail-recover"
          onClick={() => setProjectNavMode("expanded")}
          title="恢复项目栏"
          aria-label="恢复项目栏"
        >
          ≡
        </button>
      )}

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
