/**
 * NovelForge 2.0 — Motion presets
 *
 * Only animate `opacity` and `transform`. Respect
 * `prefers-reduced-motion` via accessibility.css global rule.
 */

export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.18, ease: "easeOut" as const },
};

export const listContainer = {
  hidden: { opacity: 1 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.045,
    },
  },
};

export const listItem = {
  hidden: { opacity: 0, y: 10 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.16 },
  },
};

export const drawerSlide = {
  initial: { x: "100%" },
  animate: { x: 0 },
  exit: { x: "100%" },
  transition: { duration: 0.18, ease: "easeOut" as const },
};

export const cardHover = {
  whileHover: { y: -2, scale: 1.006 },
  whileTap: { scale: 0.996 },
  transition: { duration: 0.12 },
};
