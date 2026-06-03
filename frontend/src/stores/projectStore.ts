import { create } from "zustand";
import type { Project } from "../types";
import { listProjects, getProject } from "../api";

type State = {
  projects: Project[];
  currentProjectId: number | null;
  loading: boolean;
  error: string | null;
};

type Actions = {
  refresh: () => Promise<void>;
  selectProject: (id: number | null) => Promise<void>;
  upsertProject: (p: Project) => void;
  removeProject: (id: number) => void;
};

export const useProjectStore = create<State & Actions>((set, get) => ({
  projects: [],
  currentProjectId: null,
  loading: false,
  error: null,

  refresh: async () => {
    set({ loading: true, error: null });
    try {
      const projects = await listProjects();
      set({ projects, loading: false });
      // auto-select first project if none selected
      if (!get().currentProjectId && projects.length > 0) {
        await get().selectProject(projects[0].id);
      }
    } catch (e: any) {
      set({ error: e.message ?? String(e), loading: false });
    }
  },

  selectProject: async (id: number | null) => {
    set({ currentProjectId: id });
  },

  upsertProject: (p: Project) => {
    const list = get().projects.slice();
    const idx = list.findIndex((x) => x.id === p.id);
    if (idx >= 0) list[idx] = p;
    else list.unshift(p);
    set({ projects: list });
  },

  removeProject: (id: number) => {
    set({
      projects: get().projects.filter((p) => p.id !== id),
      currentProjectId: get().currentProjectId === id ? null : get().currentProjectId,
    });
  },
}));
