/**
 * Motion for React wiring: one provider, shared timings, and the few small
 * building blocks the pages use. Spec: see the commit message of the Motion step.
 *
 * Rules (kept deliberately boring):
 *   - 150-250 ms ease-out, no springs on content, no bounce. Red sweeps for emphasis.
 *   - Animate transform and opacity only (never width/height/top/left).
 *   - Content is in the DOM from the first render. `hidden` states are opacity/translate
 *     only and animate to `show` on mount or when scrolled into view.
 *   - `prefers-reduced-motion` is honoured twice: MotionConfig reducedMotion="user"
 *     (drops transform animations) and `useInitial()` (renders the final state at once,
 *     so there is no fade either). Numbers always end on their exact value.
 */
import {
  LazyMotion, MotionConfig, useInView, useReducedMotion,
  type FeatureBundle, type Transition, type Variants,
} from "motion/react";
import * as m from "motion/react-m";
import {
  Fragment, Suspense, lazy, useEffect, useLayoutEffect, useRef, useState,
  type CSSProperties, type ElementType, type ReactNode,
} from "react";

export { m };
export { AnimatePresence } from "motion/react";

/* --------------------------------------------------------- lazy heavy APIs */

type Extras = typeof import("./motionExtras");
let extras: Extras | null = null;
let extrasPromise: Promise<Extras | null> | null = null;
/** Start (once) fetching the animate()/scroll/spring chunk; resolves null if it fails. */
export function loadExtras(): Promise<Extras | null> {
  extrasPromise ??= import("./motionExtras").then(mod => (extras = mod), () => null);
  return extrasPromise;
}

/* ------------------------------------------------------------------ timings */

export const EASE_OUT = [0.2, 0, 0, 1] as const; // matches --ease in styles.css
export const D_FAST = 0.15;
export const D_BASE = 0.22;
export const D_SLOW = 0.45;

/** Is this a pointer-capable desktop (rich motion) rather than a phone/tablet (light motion)? */
const DESKTOP_QUERY = "(min-width: 1024px) and (hover: hover) and (pointer: fine)";

export function useDesktop(): boolean {
  const [on, setOn] = useState(() => typeof window !== "undefined" && window.matchMedia(DESKTOP_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_QUERY);
    const sync = () => setOn(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return on;
}

export function useMinWidth(px: number): boolean {
  const q = `(min-width: ${px}px)`;
  const [on, setOn] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const sync = () => setOn(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [q]);
  return on;
}

/** Hover-capable pointer, independent of width (iPad with a mouse still lifts on hover). */
const HOVER_QUERY = "(hover: hover) and (pointer: fine)";
export function useCanHover(): boolean {
  const [on, setOn] = useState(() => typeof window !== "undefined" && window.matchMedia(HOVER_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(HOVER_QUERY);
    const sync = () => setOn(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return on;
}

/* ----------------------------------------------------------------- provider */

/**
 * The animation engine (domAnimation: animate, variants, exit, hover/tap/inView gestures) is
 * fetched as its own chunk right after first paint, which keeps the entry bundle small.
 * Until it arrives `m` components just hold their `initial` style, so the engine's load can
 * never leave content permanently hidden: if the chunk fails (or is very slow) we flag
 * <html class="motion-off"> and CSS forces every m-component visible (see styles.css).
 */
async function loadFeatures(): Promise<FeatureBundle> {
  const root = document.documentElement;
  const timer = window.setTimeout(() => root.classList.add("motion-off"), 4000);
  try {
    const mod = (await import("./motionFeatures")).default;
    root.classList.remove("motion-off");
    return mod;
  } catch (err) {
    console.warn("Motion features failed to load; animations disabled", err);
    root.classList.add("motion-off");
    return {} as FeatureBundle;
  } finally {
    window.clearTimeout(timer);
  }
}

export function MotionProvider({ children }: { children: ReactNode }) {
  useEffect(() => { void loadExtras(); }, []);
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: D_BASE, ease: EASE_OUT }}>
      <LazyMotion features={loadFeatures} strict>{children}</LazyMotion>
    </MotionConfig>
  );
}

/**
 * `undefined` under reduced motion (no initial state: the element renders in its final,
 * natural style at once and the enter animation is a no-op), else the given variant label.
 */
export function useInitial<T extends string>(label: T): T | undefined {
  return useReducedMotion() ? undefined : label;
}

/* ------------------------------------------------------------------ reveals */

/** Stagger step in seconds; phones get shorter staggers and a smaller travel. */
export function useStagger(): { step: number; cap: number; y: number } {
  const desktop = useDesktop();
  return desktop ? { step: 0.05, cap: 10, y: 14 } : { step: 0.03, cap: 6, y: 8 };
}

/**
 * Fade/slide a block in when it first scrolls into view. `index` staggers siblings
 * (capped so row 40 does not wait two seconds). Renders any element via `as`.
 */
export function Reveal({
  as = "div", index = 0, className, style, children, once = true, presence = false,
}: {
  as?: "div" | "li" | "section" | "tr" | "span"; index?: number; className?: string; style?: CSSProperties; children: ReactNode; once?: boolean;
  /** Inside an AnimatePresence list: also animates reordering (layout) and removal (exit opacity). */
  presence?: boolean;
}) {
  const init = useInitial("hidden");
  const { step, cap, y } = useStagger();
  const Tag = m[as] as ElementType;
  return (
    <Tag
      className={className}
      style={style}
      initial={init}
      whileInView="show"
      viewport={{ once, amount: 0.12 }}
      variants={{ hidden: { opacity: 0, y }, show: { opacity: 1, y: 0 } }}
      transition={{ duration: D_BASE, ease: EASE_OUT, delay: Math.min(index, cap) * step }}
      {...(presence ? { exit: { opacity: 0, transition: { duration: D_FAST } } } : {})}
    >
      {children}
    </Tag>
  );
}

/** Container that staggers its `StaggerItem` children (variants propagate through the tree). */
export function Stagger({ className, children, style }: { className?: string; style?: CSSProperties; children: ReactNode }) {
  const init = useInitial("hidden");
  const { step } = useStagger();
  return (
    <m.div
      className={className}
      style={style}
      initial={init}
      whileInView="show"
      viewport={{ once: true, amount: 0.05 }}
      variants={{ hidden: {}, show: { transition: { staggerChildren: step } } }}
    >
      {children}
    </m.div>
  );
}

/**
 * One staggered child. `lift` adds a hover raise (pointer devices only) and a press-in on tap.
 * Hover only changes transform; the border colour change stays in CSS.
 */
export function StaggerItem({ className, lift = false, children }: { className?: string; lift?: boolean; children: ReactNode }) {
  const { y } = useStagger();
  const canHover = useCanHover();
  return (
    <m.div
      className={className}
      variants={{ hidden: { opacity: 0, y }, show: { opacity: 1, y: 0 } }}
      whileHover={lift && canHover ? { y: -2, transition: { duration: D_FAST } } : undefined}
      whileTap={lift ? { scale: 0.985, transition: { duration: 0.1 } } : undefined}
    >
      {children}
    </m.div>
  );
}

/** Fade a loaded page in after its skeleton, so loading -> content reads as a crossfade. */
export function PageFade({ className, children }: { className?: string; children: ReactNode }) {
  const init = useInitial("hidden");
  return (
    <m.div
      className={className}
      initial={init}
      animate="show"
      variants={{ hidden: { opacity: 0 }, show: { opacity: 1 } }}
      transition={{ duration: D_BASE, ease: EASE_OUT }}
    >
      {children}
    </m.div>
  );
}

/** A card that lifts on hover (pointer devices) and presses in on tap; use around linked panels. */
export function Lift({ className, children, style }: { className?: string; children: ReactNode; style?: CSSProperties }) {
  const canHover = useCanHover();
  return (
    <m.div
      className={className}
      style={style}
      whileHover={canHover ? { y: -2, transition: { duration: D_FAST } } : undefined}
      whileTap={{ scale: 0.985, transition: { duration: 0.1 } }}
    >
      {children}
    </m.div>
  );
}

/* ----------------------------------------------------------------- numbers */

const fmt = (v: number, decimals: number) => v.toFixed(decimals);

/**
 * A number that counts up from 0 the first time it is seen, then lands on EXACTLY the
 * requested value (the last frame is always `value.toFixed(decimals)`). Later value
 * changes animate from what is on screen. Under reduced motion it just shows the value.
 * The text node is owned by this component (no React children) so the animation never
 * triggers re-renders.
 */
export function CountUp({ value, decimals = 1, className, duration = 0.7 }: {
  value: number; decimals?: number; className?: string; duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const shown = useRef<number | null>(null);        // value currently on screen (null = not animated yet)
  const reduced = useReducedMotion();
  const inView = useInView(ref, { once: true, amount: 0.2 });

  // Before first paint: always the exact value. Numbers that are on screen when the animate()
  // chunk is ready are then rewound to 0 and counted up; if the chunk is not there (slow, failed,
  // reduced motion) the final value simply stays. Nothing here can strand a wrong number.
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && shown.current == null) el.textContent = fmt(value, decimals);
  }, [value, decimals]);

  // The animate() chunk is normally already cached by the time a number mounts (route changes).
  // On a cold first load it may still be in flight: wait briefly for it, otherwise keep the real value.
  const [ready, setReady] = useState(extras != null);
  useEffect(() => {
    if (extras) return;
    let alive = true;
    const t0 = performance.now();
    loadExtras().then(x => { if (alive && x && performance.now() - t0 < 700) setReady(true); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const finish = () => { el.textContent = fmt(value, decimals); shown.current = value; };
    if (reduced) { finish(); return; }
    if (!extras || !ready) { el.textContent = fmt(value, decimals); return; }
    const first = shown.current == null;
    if (first && !inView) return;                    // below the fold: keep the real value, count when seen
    const from = first ? 0 : shown.current!;
    if (from === value) { finish(); return; }
    const controls = extras.animate(from, value, {
      duration: first ? duration : 0.35,
      ease: EASE_OUT,
      onUpdate: v => { el.textContent = fmt(v, decimals); shown.current = v; },
      onComplete: finish,
    });
    // Backstop: a throttled tab (no animation frames) must still end on the exact value.
    const backstop = window.setTimeout(() => { controls.stop(); finish(); }, (first ? duration : 0.35) * 1000 + 400);
    return () => { window.clearTimeout(backstop); controls.stop(); finish(); };
  }, [value, decimals, inView, reduced, duration, ready]);

  return <span ref={ref} className={className} />;
}

export type { Transition, Variants };


/* ------------------------------------------------------------------- shell */

/**
 * Route wrapper: fade + slight rise in, quick fade out. Used with AnimatePresence
 * mode="wait" keyed on the pathname. Under reduced motion there is no initial state and
 * no exit delay.
 */
export function RouteFade({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  const desktop = useDesktop();
  return (
    <m.div
      initial={reduced ? false : { opacity: 0, y: desktop ? 10 : 6 }}
      animate={{ opacity: 1, y: 0, transition: { duration: D_BASE, ease: EASE_OUT } }}
      exit={{ opacity: 0, transition: { duration: reduced ? 0 : 0.1, ease: "easeIn" } }}
      className="route-fade"
    >
      {children}
    </m.div>
  );
}

/** Thin red reading-progress line under the top bar (desktop only; transform: scaleX). */
const ScrollProgressImpl = lazy(() => import("./ScrollProgress"));
export function ScrollProgress() {
  return <Suspense fallback={null}><ScrollProgressImpl /></Suspense>;
}

/** Headline whose words rise in one by one (desktop); phones fade the whole line in once. */
export function Words({ text, className }: { text: string; className?: string }) {
  const init = useInitial("hidden");
  const desktop = useDesktop();
  const words = text.split(" ");
  if (!desktop) {
    return (
      <m.h1
        className={className}
        initial={init} animate="show"
        variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0 } }}
        transition={{ duration: D_BASE, ease: EASE_OUT }}
      >{text}</m.h1>
    );
  }
  return (
    <m.h1
      className={className}
      initial={init} animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.055 } } }}
    >
      {/* The space goes between the inline-block clips, not inside one: trailing whitespace inside an
          inline-block is dropped, which ran the words together ("WhowinsthenextVCTmatch?"). */}
      {words.map((w, i) => (
        <Fragment key={i}>
          <span className="word-clip">
            <m.span
              className="word"
              variants={{ hidden: { opacity: 0, y: "60%" }, show: { opacity: 1, y: 0, transition: { duration: 0.32, ease: EASE_OUT } } }}
            >{w}</m.span>
          </span>
          {i < words.length - 1 ? " " : null}
        </Fragment>
      ))}
    </m.h1>
  );
}
