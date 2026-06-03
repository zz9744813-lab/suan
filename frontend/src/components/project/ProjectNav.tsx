/**
 * ProjectNav — Round 2 sidebar (P0-UI-2 + P0-UI-3).
 *
 * Features:
 *   - Groups: 置顶 (pinned) and one bucket per category (defaults to
 *     genre for projects without an explicit category).
 *   - Search: filters projects in-place; the grouping still wraps
 *     around the matches.
 *   - Drag-and-drop: reorders items within and across buckets via
 *     @dnd-kit. A drop sends a single batched PATCH to
 *     /api/projects/reorder.
 *   - Persisted UI state: collapsed-group set lives in localStorage
 *     so refreshes keep the user's view.
 *   - Compact mode: this component renders only the avatar-strip
 *     variant when ``mode === "compact"``. The expanded list lives
 *     in a sibling component consumed by AppShell.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  DndContext, KeyboardSensor, PointerSensor,
  closestCenter, useSensor, useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext, sortableKeyboardCoordinates,
  useSortable, verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useProjectStore } from "../../stores/projectStore";
import { reorderProjects, type ProjectReorderItem } from "../../api";
import type { Project } from "../../types";

const STORAGE_COLLAPSED = "noverlforge.projectnav.collapsedGroups.v1";

type Group = {
  /** bucket key — "pinned" for the pinned section, else category */
  key: string;
  label: string;
  items: Project[];
};

/**
 * Bucket projects into a flat ordered list of groups. Pinned
 * projects are isolated into their own bucket (always first);
 * non-pinned projects group by category (falling back to genre).
 * Within a bucket, sort_order is the user-controlled order; id
 * is the tiebreaker for items that haven't been touched.
 */
function groupProjects(projects: Project[]): Group[] {
  const pinned: Project[] = [];
  const byCategory = new Map<string, Project[]>();
  for (const p of projects) {
    if (p.pinned) {
      pinned.push(p);
      continue;
    }
    const key = p.category ?? p.genre ?? "其他";
    if (!byCategory.has(key)) byCategory.set(key, []);
    byCategory.get(key)!.push(p);
  }
  const groups: Group[] = [];
  if (pinned.length > 0) {
    groups.push({ key: "pinned", label: "置顶", items: pinned });
  }
  // Sort categories by their first item's id so the bucket order is
  // stable until the user reorders. (A future enhancement could
  // surface a per-bucket sort_order; for now we just alphabetise.)
  const keys = Array.from(byCategory.keys()).sort((a, b) => a.localeCompare(b, "zh"));
  for (const key of keys) {
    groups.push({ key, label: key, items: byCategory.get(key)! });
  }
  return groups;
}

/** Apply a search filter across the flat project list. */
function filterProjects(projects: Project[], query: string): Project[] {
  if (!query.trim()) return projects;
  const q = query.trim().toLowerCase();
  return projects.filter((p) =>
    p.name.toLowerCase().includes(q) ||
    (p.genre ?? "").toLowerCase().includes(q) ||
    (p.category ?? "").toLowerCase().includes(q)
  );
}

export function ProjectNav() {
  const projects = useProjectStore((s) => s.projects);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const selectProject = useProjectStore((s) => s.selectProject);
  const location = useLocation();
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_COLLAPSED);
      return new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch { return new Set(); }
  });

  useEffect(() => {
    try { localStorage.setItem(STORAGE_COLLAPSED, JSON.stringify(Array.from(collapsed))); }
    catch { /* quota / private mode — non-fatal */ }
  }, [collapsed]);

  const filtered = useMemo(() => filterProjects(projects, query), [projects, query]);
  const groups = useMemo(() => groupProjects(filtered), [filtered]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    // Build a flat list of items in their current visual order so we
    // can locate the source and target. Items carry ``bucket`` as a
    // non-DB hint so a drop across buckets also updates ``category``
    // (and ``pinned`` for the pinned bucket).
    const flat: Array<{ id: number; bucket: string; pinned: boolean }> = [];
    for (const g of groups) {
      for (const p of g.items) flat.push({ id: p.id, bucket: g.key, pinned: g.key === "pinned" });
    }
    const oldIndex = flat.findIndex((f) => f.id === active.id);
    const newIndex = flat.findIndex((f) => f.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const moved = arrayMove(flat, oldIndex, newIndex);
    // Re-derive sort_order = index*10 (leaves room for inserts).
    // Pinned bucket → pinned=true, others → pinned=false; for the
    // pinned bucket we set category to "" so it sorts under "其他"
    // if the user unpins. Easier: just preserve each project's
    // original category unless they were dropped INTO the pinned
    // bucket, in which case we mark pinned=true but keep category.
    const byId = new Map(projects.map((p) => [p.id, p]));
    const items: ProjectReorderItem[] = moved.map((m, idx) => {
      const orig = byId.get(m.id);
      // When dragging into the pinned bucket, keep the project's
      // existing category so unpinning puts it back in the right
      // group. When dragging OUT of pinned, the bucket becomes the
      // project's category (fallback to genre).
      const category = m.bucket === "pinned"
        ? (orig?.category ?? orig?.genre ?? null)
        : (m.bucket === orig?.category ? orig?.category : m.bucket);
      return {
        project_id: m.id,
        sort_order: (idx + 1) * 10,
        category: category ?? null,
        pinned: m.bucket === "pinned",
      };
    });
    try {
      await reorderProjects(items);
      // Optimistic local re-fetch — the store's refresh is cheap.
      await useProjectStore.getState().refresh();
    } catch (e: any) {
      // Surface a useful error; the user can retry the drag.
      alert(`排序失败：${e?.message ?? String(e)}`);
    }
  };

  const toggleGroup = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const onSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <div className="projectnav-body">
        <div className="projectnav-search">
          <input
            value={query}
            onChange={onSearchChange}
            placeholder="搜索项目…"
            aria-label="搜索项目"
          />
          {query && (
            <button className="projectnav-search-clear" onClick={() => setQuery("")} title="清空">×</button>
          )}
        </div>

        {groups.length === 0 ? (
          <div className="projectnav-empty">
            {query ? "没有匹配的项目。" : "还没有项目。"}<br />
            <Link to="/projects" className="gold">新建一个</Link>
          </div>
        ) : (
          <div className="projectnav-groups">
            {groups.map((g) => (
              <div key={g.key} className="projectnav-group">
                <button
                  className="projectnav-group-head"
                  onClick={() => toggleGroup(g.key)}
                  aria-expanded={!collapsed.has(g.key)}
                >
                  <span className="projectnav-group-caret">{collapsed.has(g.key) ? "▶" : "▼"}</span>
                  <span className="projectnav-group-label">{g.label}</span>
                  <span className="projectnav-group-count">{g.items.length}</span>
                </button>
                {!collapsed.has(g.key) && (
                  <SortableContext items={g.items.map((i) => i.id)} strategy={verticalListSortingStrategy}>
                    <div className="projectnav-list">
                      {g.items.map((p) => (
                        <SortableProjectItem
                          key={p.id}
                          project={p}
                          active={p.id === currentProjectId}
                          onSelect={() => selectProject(p.id)}
                        />
                      ))}
                    </div>
                  </SortableContext>
                )}
              </div>
            ))}
          </div>
        )}

        {/* hidden route so React Router doesn't complain about the import */}
        <span style={{ display: "none" }}>{location.pathname}</span>
      </div>
    </DndContext>
  );
}

/** One row in the project list — wraps the existing card UI in a
 *  drag handle so the user can grab anywhere on the row. */
function SortableProjectItem({
  project, active, onSelect,
}: { project: Project; active: boolean; onSelect: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: project.id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`projectnav-item-wrap ${isDragging ? "dragging" : ""}`}
      {...attributes}
      {...listeners}
    >
      <button
        className={`projectnav-item ${active ? "active" : ""}`}
        onClick={onSelect}
        title={project.name}
      >
        <div className="projectnav-item-name ellipsis">
          {project.pinned && <span className="projectnav-pin" title="置顶">📌</span>}
          {project.name}
        </div>
        <div className="projectnav-item-meta">
          <span className="badge gold tiny">{project.genre}</span>
          <span className="tiny muted">{project.chapter_count}章 · {formatNumber(project.total_words)}字</span>
        </div>
        <div className="projectnav-item-bar">
          <div
            className="projectnav-item-bar-fill"
            style={{ width: `${Math.min(100, (project.total_words / project.target_word_count) * 100)}%` }}
          />
        </div>
      </button>
    </div>
  );
}

function formatNumber(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`;
  return n.toLocaleString();
}
