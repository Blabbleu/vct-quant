/** Return an in-app anchor pathname when it is safe to prefetch. */
export function linkPath(
  anchor: { pathname: string; origin: string; target: string } | null,
  pageOrigin: string,
): string | null {
  if (!anchor || anchor.target === "_blank" || anchor.origin !== pageOrigin) return null;
  return anchor.pathname;
}
