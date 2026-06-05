/**
 * ReviewDebugMenu — 调试菜单 (NF2 阶段4)
 *
 * 下拉菜单: "手动补跑5读者评审" / "手动补跑主Agent接入" / "重新分组" / "重新触发讨论"
 * 调用对应 API
 */
import { useState } from "react";
import { api } from "../../api/client";

type MenuItem = {
  key: string;
  label: string;
  endpoint: string;
  body?: Record<string, unknown>;
};

const MENU_ITEMS: MenuItem[] = [
  {
    key: "run_readers",
    label: "手动补跑5读者评审",
    endpoint: "/api/reviews/run-readers",
    body: {},
  },
  {
    key: "run_chief",
    label: "手动补跑主Agent接入",
    endpoint: "/api/reviews/run-chief",
    body: {},
  },
  {
    key: "regroup",
    label: "重新分组",
    endpoint: "/api/reviews/regroup",
    body: {},
  },
  {
    key: "retrigger_discussion",
    label: "重新触发讨论",
    endpoint: "/api/reviews/trigger-discussion",
    body: {},
  },
];

export function ReviewDebugMenu({ projectId, chapterId }: { projectId: number; chapterId: number }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const handleAction = async (item: MenuItem) => {
    setLoading(item.key);
    setResult(null);
    try {
      const body = { project_id: projectId, chapter_id: chapterId, ...item.body };
      await api.post<any>(item.endpoint, body);
      setResult(`${item.label}: 成功`);
    } catch (e: any) {
      setResult(`${item.label}: 失败 — ${e.message || "未知错误"}`);
    }
    setLoading(null);
    setOpen(false);
  };

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button
        className="small"
        onClick={() => setOpen(!open)}
        style={{ position: "relative" }}
      >
        调试
        <span style={{ marginLeft: 4, fontSize: 10 }}>▼</span>
      </button>

      {open && (
        <>
          <div
            style={{ position: "fixed", inset: 0, zIndex: 999 }}
            onClick={() => setOpen(false)}
          />
          <div
            style={{
              position: "absolute",
              top: "100%",
              right: 0,
              marginTop: 4,
              background: "var(--bg-card, #fff)",
              border: "1px solid var(--border, #ddd)",
              borderRadius: 4,
              boxShadow: "0 4px 12px rgba(0,0,0,0.12)",
              zIndex: 1000,
              minWidth: 200,
            }}
          >
            {MENU_ITEMS.map((item) => (
              <button
                key={item.key}
                style={{
                  display: "block",
                  width: "100%",
                  padding: "8px 12px",
                  border: "none",
                  background: "none",
                  textAlign: "left",
                  fontSize: 12,
                  cursor: loading ? "wait" : "pointer",
                  opacity: loading && loading !== item.key ? 0.5 : 1,
                }}
                onClick={() => handleAction(item)}
                disabled={!!loading}
              >
                {loading === item.key ? "运行中..." : item.label}
              </button>
            ))}
          </div>
        </>
      )}

      {result && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            marginTop: 4,
            fontSize: 11,
            padding: "4px 8px",
            borderRadius: 3,
            background: "var(--bg-surface, #f5f5f5)",
            whiteSpace: "nowrap",
            zIndex: 999,
          }}
        >
          {result}
        </div>
      )}
    </div>
  );
}
