// Heavier Motion APIs (hybrid animate(), scroll + spring) kept out of the entry chunk.
// Loaded right after first paint by MotionProvider; consumers treat them as optional.
export { animate, useScroll, useSpring } from "motion/react";
