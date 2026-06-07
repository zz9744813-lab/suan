/**
 * P4 — 模型配置页组件 (spec 05 §12)
 *
 *   - AgentAvatar                虚拟头像 (8 样式 × 7 状态)
 *   - ProviderAccordion          Provider 折叠摘要
 *   - AgentRoleMatrix            角色绑定矩阵
 *   - AgentRoleRow               矩阵单行
 *   - AgentRunDetailPanel        选中 Agent 的详细面板 (右侧)
 *   - AgentRoleEditor            新增/编辑 Agent 的弹窗
 *   - BindingModeSwitch          模型绑定模式切换
 *   - AutoStrategySelect         自动策略选择下拉
 *   - CandidateProviderPicker    候选 Provider 多选器
 *   - CandidateModelPoolEditor   候选模型池编辑器
 *   - FallbackCandidateEditor    Fallback 候选编辑器
 *   - ModelSelectionPreviewPanel 模型选择预览面板
 *   - ModelFailoverTimeline      Failover 时间线
 *   - ProviderHealthFullModal    Provider 完整健康检查弹窗
 *   - AutoConfigureToolbar       一键自动配置工具栏
 *   - CircuitBreakerBadge        熔断器状态徽标
 */
export { AgentAvatar } from "./AgentAvatar";
export { ProviderAccordion } from "./ProviderAccordion";
export { AgentRoleMatrix } from "./AgentRoleMatrix";
export { AgentRoleRow } from "./AgentRoleRow";
export { AgentRunDetailPanel } from "./AgentRunDetailPanel";
export { AgentRoleEditor } from "./AgentRoleEditor";
export { AgentRoleEditorModal } from "./AgentRoleEditorModal";
export { BindingModeSwitch } from "./BindingModeSwitch";
export { AutoStrategySelect } from "./AutoStrategySelect";
export { CandidateProviderPicker } from "./CandidateProviderPicker";
export { CandidateModelPoolEditor } from "./CandidateModelPoolEditor";
export { FallbackCandidateEditor } from "./FallbackCandidateEditor";
export { ModelSelectionPreviewPanel } from "./ModelSelectionPreviewPanel";
export { ModelFailoverTimeline } from "./ModelFailoverTimeline";
export { ProviderHealthFullModal } from "./ProviderHealthFullModal";
export { AutoConfigureToolbar } from "./AutoConfigureToolbar";
export { CircuitBreakerBadge } from "./CircuitBreakerBadge";
export { FirstRunGuide } from "./FirstRunGuide";
export { ProviderModelPicker } from "./ProviderModelPicker";
export { AutoConfigureModal } from "./AutoConfigureModal";
// P-Delete-Preview: project-styled confirmation dialog used by the
// Provider delete flow (replaces the native `confirm()` in
// ``ModelsPage``).
export { ConfirmDialog } from "./ConfirmDialog";
