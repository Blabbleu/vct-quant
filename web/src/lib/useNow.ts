import { useEffect, useState } from "react";

/** Wall-clock ms, re-read every `every` ms (a ticking countdown; text only, no animation). */
export function useNow(every = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), every);
    return () => window.clearInterval(id);
  }, [every]);
  return now;
}
