/**
 * AgentAvatar — Agent 虚拟头像 (P4 §13)
 *
 * 8 种 avatar_style × 7 种 status, 用 inline SVG + CSS class
 * 区分. 不依赖图片资源, 暗色背景友好.
 *
 * 状态视觉 (P4 §13):
 *   idle      低饱和灰
 *   queued    橙色边框
 *   running   发光 / 呼吸
 *   succeeded 绿色
 *   failed    红色
 *   disabled  灰色
 *   waiting   蓝色脉冲
 */
import type { AgentAvatarStyle, AgentStatus } from "../../types";
import "./AgentAvatar.css";

export function AgentAvatar({
  style, status, size = 32, title,
}: {
  style: AgentAvatarStyle | null | undefined;
  status: AgentStatus | string;
  size?: number;
  title?: string;
}) {
  const s = style ?? "orb";
  return (
    <span className="agent-avatar" data-status={status} data-style={s} title={title}>
      <svg width={size} height={size} viewBox="0 0 40 40">
        {renderAvatarShape(s)}
      </svg>
    </span>
  );
}

// 8 种 avatar 形状 — 都用 SVG 走, 简单但能区分
function renderAvatarShape(style: AgentAvatarStyle): React.ReactNode {
  switch (style) {
    case "orb":
      return <circle cx="20" cy="20" r="14" />;
    case "robot":
      return (
        <g>
          <rect x="8" y="12" width="24" height="20" rx="3" />
          <circle cx="14" cy="20" r="2" fill="currentColor" />
          <circle cx="26" cy="20" r="2" fill="currentColor" />
          <rect x="16" y="26" width="8" height="2" />
          <line x1="20" y1="12" x2="20" y2="6" />
          <circle cx="20" cy="5" r="1.5" fill="currentColor" />
        </g>
      );
    case "scribe":
      return (
        <g>
          <path d="M 12 28 L 20 12 L 28 28 Z" />
          <line x1="20" y1="12" x2="20" y2="32" stroke="currentColor" strokeWidth="1" />
        </g>
      );
    case "critic":
      return (
        <g>
          <line x1="20" y1="6" x2="20" y2="34" stroke="currentColor" strokeWidth="2" />
          <rect x="8" y="14" width="9" height="4" />
          <rect x="23" y="22" width="9" height="4" />
        </g>
      );
    case "memory_core":
      return (
        <g>
          <polygon points="20,4 34,12 34,28 20,36 6,28 6,12" />
          <circle cx="20" cy="20" r="5" fill="currentColor" />
        </g>
      );
    case "study_core":
      return (
        <g>
          <circle cx="20" cy="20" r="13" />
          <line x1="20" y1="20" x2="20" y2="6" stroke="currentColor" strokeWidth="1.5" />
          <line x1="20" y1="20" x2="30" y2="20" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="20" cy="20" r="2" fill="currentColor" />
        </g>
      );
    case "discussion_core":
      return (
        <g>
          <circle cx="12" cy="20" r="6" />
          <circle cx="28" cy="20" r="6" />
          <circle cx="20" cy="10" r="4" />
        </g>
      );
    case "custom":
    default:
      return (
        <g>
          <polygon points="20,4 24,16 36,16 26,24 30,36 20,28 10,36 14,24 4,16 16,16" />
        </g>
      );
  }
}
