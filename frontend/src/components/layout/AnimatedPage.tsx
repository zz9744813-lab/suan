import { motion } from "framer-motion";
import { pageTransition } from "../../lib/motion";

type AnimatedPageProps = {
  children: React.ReactNode;
};

export function AnimatedPage({ children }: AnimatedPageProps) {
  return (
    <motion.div
      className="animated-page"
      initial={pageTransition.initial}
      animate={pageTransition.animate}
      exit={pageTransition.exit}
      transition={pageTransition.transition}
    >
      {children}
    </motion.div>
  );
}
