import { shortName } from "../TeamName";

/**
 * Team tag/name label. Tag is the default look; teams with no tag (T1, NRG,
 * MIBR, Mega Minors) fall back to their (already short) name. Long names
 * always truncate on one line; screen readers get the full name either way.
 */
export default function TeamLabel({ name, tag, mode = "tag" }: {
  name: string; tag?: string | null; mode?: "tag" | "full" | "auto";
}) {
  const short = shortName(name, tag);
  const display = mode === "full" ? name : (short ?? name);
  return (
    <span className="team-label ellipsis" aria-label={name} title={name}>
      {display}
    </span>
  );
}
