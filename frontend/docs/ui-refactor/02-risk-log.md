# UI Refactor Risk Log

## RISK-001: AppShell display:block!important removal
- **Severity**: P0
- **Description**: The "Final placement guard" (AppShell.css line 584-597) overrides `display:grid` with `display:block!important`, forcing all children to use fixed positioning. Removing it could break layout if hot-reload or profile CSS interferes.
- **Mitigation**: Replace with `box-sizing: border-box` guard only. Keep `position:fixed` on the shell container but let grid handle child placement. Test hot-reload before committing.

## RISK-002: .card class rename in Dashboard
- **Severity**: P1
- **Description**: Renaming `.card` to `.dashboard-card` in Dashboard.css and Dashboard.tsx affects only Dashboard, but Dashboard sub-components (FailureDiagnosisCard, etc.) may also reference `.card`.
- **Mitigation**: Search all Dashboard sub-components for `.card` references. Only rename Dashboard-specific usage.

## RISK-003: Global .card class used in 15+ pages
- **Severity**: P2
- **Description**: The global `.card` class is used in ChapterDetail, GraphsPage, PromptsPage, StudyPage, WorkerPage, TasksPage, ProjectPage. Changing it globally would be a big-bang refactor.
- **Mitigation**: Phase 1 only fixes the Dashboard conflict. Other pages keep using global `.card` until Phase 3 Card component is ready. New code uses `<Card>` component.

## RISK-004: Lazy loading named exports
- **Severity**: P1
- **Description**: Many pages use named exports (e.g., `export function Dashboard`). React.lazy() requires default exports.
- **Mitigation**: Use `.then(m => ({ default: m.ComponentName }))` pattern for named exports.

## RISK-005: Framer Motion bundle size
- **Severity**: P2
- **Description**: framer-motion adds ~30KB gzipped. Could impact first paint.
- **Mitigation**: Isolate in manualChunks. Only use on core transitions, not every list item.

## RISK-006: CSS variable naming migration
- **Severity**: P2
- **Description**: Adding new semantic tokens (--color-accent-primary) while keeping old names (--accent-gold) creates dual naming. Old code continues working, but new code must use new names.
- **Mitigation**: Document mapping. ESLint rule (future) to warn on deprecated names.
