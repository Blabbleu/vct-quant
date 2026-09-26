/**
 * A team's name with its vlr.gg tag (Paper Rex -> PRX).
 * mode "full": "Paper Rex PRX" (tag as a small chip);
 * mode "auto": full name where there is room, tag where space is tight;
 * mode "tag": tag only (full name in the tooltip).
 * vlr.gg leaves the tag empty when the name is already short (T1, MIBR, ENVY);
 * such names stand in for the tag.
 */
export function shortName(name: string, tag?: string | null): string | null {
  if (tag) return tag;
  return name.length <= 6 ? name : null;
}

export default function TeamName({ name, tag, mode = "full" }: {
  name: string; tag?: string | null; mode?: "full" | "auto" | "tag";
}) {
  const short = shortName(name, tag);
  const redundant = !short || short.toLowerCase() === name.toLowerCase();
  if (mode === "tag" && short) return <span className="tn" title={name}><span className="tn-short">{short}</span></span>;
  if (redundant) return <span className="tn" title={name}><span className="tn-full">{name}</span></span>;
  return (
    <span className={`tn ${mode}`} title={`${name} (${short})`}>
      <span className="tn-full">{name}</span>
      {mode === "auto" ? <span className="tn-short">{short}</span> : <span className="tn-tag">{short}</span>}
    </span>
  );
}
