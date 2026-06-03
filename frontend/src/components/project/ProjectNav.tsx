/**
 * ProjectNav — Round 2 sidebar (P0-UI-2 + P0-UI-3) + Round F fix
 * (P1-2 cross-group drag).
 *
 * Features:
 *   - Groups: 置顶 (pinned) and one bucket per category (defaults to
 *     genre for projects without an explicit category).
 *   - Search: filters projects in-place; the grouping still wraps
 *     around the matches.
 *   - Drag-and-drop: reorders items within AND across buckets via
 *     @dnd-kit. A drop sends a single batched PATCH to
 *     /api/projects/reorder.
 *   - Cross-group drag (Round F): DnD ids are namespaced as
 *     ``project:{id}`` and ``group:{key}`` so a drop onto a GROUP
 *     (e.g. an empty group, or a group's header) is distinguishable
 *     from a drop onto another project. Groups are themselves
 *     ``useDroppable`` so empty groups are still valid drop targets.
 *     ``onDragEnd`` re-derives each item's bucket based on its
 *     final position, not its original position.
 *   - Persisted UI state: collapsed-group set lives in localStorage
 *     so refreshes keep the user's view.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  DndContext, KeyboardSensor, PointerSensor,
  closestCenter, useSensor, useSensors,
  useDroppable,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext, sortableKeyboardCoordinates,
  useSortable, verticalListSortingStrategy,
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

const PROJECT_ID_PREFIX = "project:";
const GROUP_ID_PREFIX = "group:";

/** Bucket projects into a flat ordered list of groups. Pinned
 *  projects are isolated into their own bucket (always first);
 *  non-pinned projects group by category (falling back to genre). */
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
  // Alphabetical category order keeps the bucket order stable until
  // the user reorders. A future enhancement could surface a per-bucket
  // sort_order; for now we just alphabetise.
  const keys = Array.from(byCategory.keys()).sort((a, b) => a.localeCompare(b, "zh"));
  for (const key of keys) {
    groups.push({ key, label: key, items: byCategory.get(key)! });
  }
  return groups;
}

function filterProjects(projects: Project[], query: string): Project[] {
  if (!query.trim()) return projects;
  const q = query.trim().toLowerCase();
  return projects.filter((p) =>
    p.name.toLowerCase().includes(q) ||
    (p.genre ?? "").toLowerCase().includes(q) ||
    (p.category ?? "").toLowerCase().includes(q)
  );
}

/** Parse a DnD id back into its kind + raw key. Returns null on
 *  unknown format. */
function parseId(id: string | number): { kind: "project" | "group"; key: number | string } | null {
  const s = String(id);
  if (s.startsWith(PROJECT_ID_PREFIX)) {
    const n = Number(s.slice(PROJECT_ID_PREFIX.length));
    if (Number.isFinite(n)) return { kind: "project", key: n };
    return null;
  }
  if (s.startsWith(GROUP_ID_PREFIX)) {
    return { kind: "group", key: s.slice(GROUP_ID_PREFIX.length) };
  }
  return null;
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

  // P15 / Round F: cross-group drag handler. The previous
  // implementation used ``arrayMove(flat, ...)`` which moves order
  // but leaves each item's ``bucket`` field set to the SOURCE bucket.
  // That meant dropping a project from group A into group B was
  // persisted as "moved within A" because the rebuilt layout
  // recomputed each item's bucket from the unchanged source field.
  // The fix: extract source/target groups + indices, splice the
  // project from source to target, then derive each item's new
  // bucket from the resulting layout (NOT from the original
  // source). This way dropping onto an empty group's drop zone
  // (id = ``group:{key}``) is also handled — we just append.
  const onDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const activeParsed = parseId(active.id);
    const overParsed = parseId(over.id);
    if (!activeParsed || activeParsed.kind !== "project") return;
    if (!overParsed) return;
    const sourceId = activeParsed.key as number;
    // Same-project no-op
    if (overParsed.kind === "project" && overParsed.key === sourceId) return;

    // 1. Find the source group and the index within it.
    const sourceGroupIdx = groups.findIndex((g) =>
      g.items.some((p) => p.id === sourceId),
    );
    if (sourceGroupIdx < 0) return;
    const sourceGroup = groups[sourceGroupIdx];
    const sourceItem = sourceGroup.items.find((p) => p.id === sourceId)!;

    // 2. Find the target group + index. Three cases:
    //    a) drop on another project → use that project's group + position
    //    b) drop on a group drop zone → use that group's end position
    //    c) drop outside any known target → no-op
    let targetGroupIdx: number;
    let targetWithinIdx: number; // 0-based index WITHIN the target group's items
    if (overParsed.kind === "group") {
      const groupKey = overParsed.key as string;
      // The "pinned" group key is a special value. We need to find
      // the group with matching key OR, if the source was already in
      // the pinned group, find the pinned group in the rebuilt list.
      const idx = groups.findIndex((g) => g.key === groupKey);
      if (idx < 0) return;
      targetGroupIdx = idx;
      // Drop at the END of the target group (the user can fine-tune
      // by dropping on a specific item in the same group).
      targetWithinIdx = groups[idx].items.length;
    } else {
      // over is a project. Find its group.
      const tgt = overParsed.key as number;
      const idx = groups.findIndex((g) =>
        g.items.some((p) => p.id === tgt),
      );
      if (idx < 0) return;
      targetGroupIdx = idx;
      const withinIdx = groups[idx].items.findIndex((p) => p.id === tgt);
      targetWithinIdx = withinIdx < 0 ? groups[idx].items.length : withinIdx;
    }

    // 3. Build the new layout. We deep-clone ``groups`` to avoid
    //    mutating the memoised array, then splice the moved item.
    const next: Group[] = groups.map((g) => ({ ...g, items: [...g.items] }));
    next[sourceGroupIdx].items = next[sourceGroupIdx].items.filter(
      (p) => p.id !== sourceId,
    );
    // If the source and target are the same group, the removal above
    // shifted the target index left by one. Re-resolve.
    if (sourceGroupIdx === targetGroupIdx) {
      if (targetWithinIdx > next[targetGroupIdx].items.length) {
        targetWithinIdx = next[targetGroupIdx].items.length;
      }
    } else {
      // Different groups: clamp to the target group's current length.
      if (targetWithinIdx > next[targetGroupIdx].items.length) {
        targetWithinIdx = next[targetGroupIdx].items.length;
      }
    }
    next[targetGroupIdx].items.splice(targetWithinIdx, 0, sourceItem);

    // 4. Flatten and build the reorder payload. For each project,
    //    its bucket = the group key it now lives in, NOT the
    //    original. Pinned bucket → pinned=true, others → pinned=false.
    //    Category for the pinned bucket is preserved from the
    //    project (so unpinning puts it back in the right place).
    const byId = new Map(projects.map((p) => [p.id, p]));
    const items: ProjectReorderItem[] = [];
    let globalIdx = 0;
    for (const g of next) {
      for (const p of g.items) {
        const orig = byId.get(p.id);
        let category: string | null;
        let pinned: boolean;
        if (g.key === "pinned") {
          pinned = true;
          // Keep the project's existing category so unpinning
          // drops it back into the right group.
          category = orig?.category ?? orig?.genre ?? null;
        } else {
          pinned = false;
          // The new group key IS the new category (or null if the
          // group key is "" / "__none__"). For now any non-pinned
          // group key is a real category string.
          category = g.key;
        }
        items.push({
          project_id: p.id,
          sort_order: (++globalIdx) * 10,
          category,
          pinned,
        });
      }
    }
    try {
      await reorderProjects(items);
      await useProjectStore.getState().refresh();
    } catch (e: any) {
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
              <ProjectGroup
                key={g.key}
                group={g}
                currentProjectId={currentProjectId}
                selectProject={selectProject}
                collapsed={collapsed.has(g.key)}
                onToggle={() => toggleGroup(g.key)}
              />
            ))}
          </div>
        )}

        {/* hidden route so React Router doesn't complain about the import */}
        <span style={{ display: "none" }}>{location.pathname}</span>
      </div>
    </DndContext>
  );
}

/** A single bucket: a header (collapse toggle + drop zone) and a
 *  SortableContext of the bucket's items. The whole group is a
 *  droppable so dropping onto an empty group or the header itself
 *  still resolves to the right bucket. */
function ProjectGroup({
  group, currentProjectId, selectProject, collapsed, onToggle,
}: {
  group: Group;
  currentProjectId: number | null;
  selectProject: (id: number) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  // useDroppable makes the group container a valid drop target with
  // id = "group:{key}". We need this because a SortableContext only
  // knows about its own items, not "the empty space below them" or
  // "the group header above them".
  const { setNodeRef, isOver } = useDroppable({ id: `${GROUP_ID_PREFIX}${group.key}` });
  return (
    <div
      ref={setNodeRef}
      className={`projectnav-group ${isOver ? "drag-over" : ""}`}
    >
      <button
        className="projectnav-group-head"
        onClick={onToggle}
        aria-expanded={!collapsed}
      >
        <span className="projectnav-group-caret">{collapsed ? "▶" : "▼"}</span>
        <span className="projectnav-group-label">{group.label}</span>
        <span className="projectnav-group-count">{group.items.length}</span>
      </button>
      {!collapsed && (
        <SortableContext
          items={group.items.map((i) => `${PROJECT_ID_PREFIX}${i.id}`)}
          strategy={verticalListSortingStrategy}
        >
          <div className="projectnav-list">
            {group.items.map((p) => (
              <SortableProjectItem
                key={p.id}
                project={p}
                active={p.id === currentProjectId}
                onSelect={() => selectProject(p.id)}
              />
            ))}
            {group.items.length === 0 && (
              <div className="projectnav-list-empty muted tiny">（空）</div>
            )}
          </div>
        </SortableContext>
      )}
    </div>
  );
}

function SortableProjectItem({
  project, active, onSelect,
}: { project: Project; active: boolean; onSelect: () => void }) {
  // Round F: useSortable now keys on the prefixed id so collision
  // detection in DndContext can match active/over to the same item.
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: `${PROJECT_ID_PREFIX}${project.id}`,
  });
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
