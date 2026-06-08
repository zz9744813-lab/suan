import { Link } from "react-router-dom";
import type { DomainLink } from "../../lib/domainMap";
import "../workbench/DomainWorkbench.css";

export function DomainBreadcrumb({ current, links = [] }: { current: string; links?: DomainLink[] }) {
  return (
    <nav className="domain-breadcrumb" aria-label="域导航面包屑">
      <Link to="/dashboard">总编首页</Link>
      <span>/</span>
      <span>{current}</span>
      {links.length > 0 && (
        <div className="domain-breadcrumb-links">
          {links.slice(0, 3).map((link) => (
            <Link key={link.to} to={link.to}>{link.label}</Link>
          ))}
        </div>
      )}
    </nav>
  );
}
