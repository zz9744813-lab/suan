import { useEffect, useState } from "react";
import { getWorkbenchOverview, type WorkbenchOverviewParams } from "../api/workbench";
import type { WorkbenchOverview } from "../types/workbench";

export interface UseWorkbenchOverviewOptions extends WorkbenchOverviewParams {
  refreshMs?: number;
  enabled?: boolean;
}

export function useWorkbenchOverview({
  projectId = null,
  domain = null,
  refreshMs = 8000,
  enabled = true,
}: UseWorkbenchOverviewOptions = {}) {
  const [data, setData] = useState<WorkbenchOverview | null>(null);
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading((prev) => prev || !data);
      setError(null);
      try {
        const next = await getWorkbenchOverview({ projectId, domain });
        if (!cancelled) setData(next);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const interval = refreshMs > 0 ? window.setInterval(load, refreshMs) : null;
    return () => {
      cancelled = true;
      if (interval) window.clearInterval(interval);
    };
  }, [projectId, domain, refreshMs, enabled]);

  return { data, loading, error, reload: () => getWorkbenchOverview({ projectId, domain }).then(setData) };
}
