import { getWorkbenchDomain } from "../../lib/domainMap";
import { DomainWorkbenchLayout } from "../../components/workbench/DomainWorkbenchLayout";

export function GovernanceWorkbenchPage() {
  return <DomainWorkbenchLayout domain={getWorkbenchDomain("governance")} />;
}
