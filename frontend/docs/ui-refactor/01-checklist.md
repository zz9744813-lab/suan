# UI Refactor Checklist

## Phase 0: Baseline Protection
- [x] Record page inventory
- [x] Create smoke test scaffold
- [x] Create layout test scaffold
- [ ] Create accessibility test scaffold

## Phase 1: Token & Global CSS Fix
- [x] Add missing radius tokens (--radius-xs, --radius-2xl, --radius-full)
- [x] Add semantic color aliases (--color-accent-primary, etc.)
- [x] Add surface/border semantic tokens
- [x] Update font stack (Chinese-first)
- [x] Fix .card conflict (Dashboard → .dashboard-card)
- [x] Keep deprecated aliases
- [ ] Add accessibility.css base

## Phase 2: AppShell Layout
- [ ] Remove display:block!important guard
- [ ] Clean grid placement
- [ ] Add responsive breakpoints (1280/1100/860/720)
- [ ] Add mobile bottom nav placeholder
- [ ] Verify 1440/1024/768/390 viewports

## Phase 3: UI Component Library
- [ ] Button
- [ ] Card
- [ ] Input
- [ ] Badge/Pill
- [ ] Modal
- [ ] Drawer
- [ ] Skeleton
- [ ] EmptyState
- [ ] ErrorState
- [ ] Spinner
- [ ] Tabs
- [ ] Tooltip
- [ ] Pilot migration: Dashboard

## Phase 4: Page State Experience
- [ ] Toast system
- [ ] Dashboard: Skeleton/EmptyState/ErrorState
- [ ] ProjectsPage: Skeleton/EmptyState/ErrorState
- [ ] ModelConfig: Skeleton/EmptyState/ErrorState
- [ ] WorkerDashboard: Skeleton/EmptyState/ErrorState

## Phase 5: Motion System
- [ ] Install framer-motion
- [ ] Create src/lib/motion.ts
- [ ] Page transitions
- [ ] Card micro-interactions
- [ ] List stagger
- [ ] Drawer animation

## Phase 6: Accessibility
- [ ] accessibility.css (skip-link, focus-visible, reduced-motion)
- [ ] AppShell skip-link
- [ ] aria-live region
- [ ] Modal focus trap
- [ ] Form aria bindings

## Phase 7: Performance
- [ ] Route-level lazy loading
- [ ] PageSkeleton
- [ ] Vite manual chunks
- [ ] CSS containment
- [ ] Long list virtualization scaffold

## Phase 8: Page Migration
- [ ] RailNav: remove emoji, use stable symbols
- [ ] Dashboard: Card/Button migration
- [ ] ProjectsPage: Card/Button migration
- [ ] ModelConfig: Card/Button/Badge migration
- [ ] WorkerDashboard: Card/Badge migration

## Phase 9: Testing & Docs
- [ ] Unit tests for UI components
- [ ] E2E smoke tests
- [ ] Responsive viewport tests
- [ ] Accessibility (axe-core) tests
- [ ] Visual regression (Playwright screenshots)
