import { NavLink } from "react-router-dom";
import "./MobileBottomNav.css";

const items = [
  { to: "/dashboard", label: "工作台", icon: "\u25C7" },
  { to: "/projects", label: "项目", icon: "\u25A6" },
  { to: "/tasks", label: "任务", icon: "\u25A4" },
  { to: "/models", label: "模型", icon: "\u25C8" },
];

export function MobileBottomNav() {
  return (
    <nav className="mobile-bottom-nav" aria-label="移动端主导航">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            `mobile-bottom-nav__item${isActive ? " active" : ""}`
          }
        >
          <span className="mobile-bottom-nav__icon" aria-hidden="true">
            {item.icon}
          </span>
          <span className="mobile-bottom-nav__label">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
