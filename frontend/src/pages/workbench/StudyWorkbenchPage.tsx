import { getWorkbenchDomain } from "../../lib/domainMap";
import { DomainWorkbenchLayout } from "../../components/workbench/DomainWorkbenchLayout";

export function StudyWorkbenchPage() {
  return <DomainWorkbenchLayout domain={getWorkbenchDomain("study")} />;
}
