import { getWorkbenchDomain } from "../../lib/domainMap";
import { DomainWorkbenchLayout } from "../../components/workbench/DomainWorkbenchLayout";

export function FeedbackWorkbenchPage() {
  return <DomainWorkbenchLayout domain={getWorkbenchDomain("feedback")} />;
}
