import { NavLink, useLocation } from "react-router-dom";
import { WORKBENCH_DOMAINS } from "../../lib/domainMap";
import "./MobileBottomNav.css";

const legacyRoutePrefixes: Record<string, string[]> = {
  writing: ["/projects", "/tasks", "/worker"],
  study: ["/study", "/graphs", "/graph", "/behavior"],
  feedback: ["/reviews", "/discussion", "/reader-agents"],
  memory: ["/memory", "/memory-shelf"],
  governance: ["/models", "/prompts", "/prompts-matrix", "/model-observability", "/audit"],
};

export function MobileBottomNav() {
  const location = useLocation();
  return (
    <nav className="mobile-bottom-nav" aria-label="移动端主导航">
      <NavLink
        to="/dashboard"
        className={({ isActive }) => `mobile-bottom-nav__item${isActive ? " active" : ""}`}
      >
        <span className="mobile-bottom-nav__icon" aria-hidden="true">⌂</span>
        <span className="mobile-bottom-nav__label">首页</span>
      </NavLink>
      {WORKBENCH_DOMAINS.map((domain) => {
        const active = location.pathname.startsWith(domain.path) || legacyRoutePrefixes[domain.key]?.some((prefix) => location.pathname.startsWith(prefix));
        return (
          <NavLink
            key={domain.key}
            to={domain.path}
            className={() => `mobile-bottom-nav__item${active ? " active" : ""}`}
          >
            <span className="mobile-bottom-nav__icon" aria-hidden="true">
              {domain.navIcon}
            </span>
            <span className="mobile-bottom-nav__label">{domain.shortLabel}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
