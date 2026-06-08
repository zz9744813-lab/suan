import { getWorkbenchDomain } from "../../lib/domainMap";
import { DomainWorkbenchLayout } from "../../components/workbench/DomainWorkbenchLayout";

export function WritingWorkbenchPage() {
  return <DomainWorkbenchLayout domain={getWorkbenchDomain("writing")} />;
}
