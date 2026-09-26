import type { ReactNode } from "react";

/** H2, uppercase +0.06em, followed by a hairline rule, with optional trailing content. */
export default function SectionHead({ title, right }: { title: ReactNode; right?: ReactNode }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {right && <div className="section-head-right">{right}</div>}
    </div>
  );
}
