import { useState } from "react";
import "./Tabs.css";

export type Tab = {
  key: string;
  label: string;
  content: React.ReactNode;
};

export type TabsProps = {
  tabs: Tab[];
  defaultKey?: string;
  className?: string;
};

export function Tabs({ tabs, defaultKey, className = "" }: TabsProps) {
  const [active, setActive] = useState(defaultKey ?? tabs[0]?.key ?? "");
  const current = tabs.find((t) => t.key === active);

  return (
    <div className={["ui-tabs", className].join(" ")}>
      <div className="ui-tabs__list" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={tab.key === active}
            className={["ui-tabs__tab", tab.key === active ? "ui-tabs__tab--active" : ""].join(" ")}
            onClick={() => setActive(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="ui-tabs__panel" role="tabpanel">
        {current?.content}
      </div>
    </div>
  );
}
