import * as m from "motion/react-m";
import { useScroll, useSpring } from "motion/react";

/** Scroll-linked progress: scrollYProgress -> spring -> scaleX (transform only). */
export default function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 220, damping: 34, restDelta: 0.0005 });
  return <m.div className="scroll-progress" style={{ scaleX }} aria-hidden="true" />;
}
