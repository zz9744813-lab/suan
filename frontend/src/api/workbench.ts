import { api } from "./client";
import type { WorkbenchDomainKey, WorkbenchOverview } from "../types/workbench";

export interface WorkbenchOverviewParams {
  projectId?: number | null;
  domain?: WorkbenchDomainKey | null;
}

export async function getWorkbenchOverview(params: WorkbenchOverviewParams = {}) {
  const search = new URLSearchParams();
  if (params.projectId != null) search.set("project_id", String(params.projectId));
  if (params.domain) search.set("domain", params.domain);
  const qs = search.toString();
  return api.get<WorkbenchOverview>(`/api/workbench/overview${qs ? `?${qs}` : ""}`);
}
