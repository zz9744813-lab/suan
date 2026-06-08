import { getWorkbenchDomain } from "../../lib/domainMap";
import { DomainWorkbenchLayout } from "../../components/workbench/DomainWorkbenchLayout";

export function MemoryWorkbenchPage() {
  return <DomainWorkbenchLayout domain={getWorkbenchDomain("memory")} />;
}
