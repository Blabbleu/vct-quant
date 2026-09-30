import { useState } from "react";
import "./AgentIcon.css";

function slug(agent: string) {
  return agent.split(",", 1)[0].toLowerCase().replace(/[^a-z]/g, "");
}

export default function AgentIcon({ agent, size = 24 }: { agent: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const name = agent?.trim() || "Unknown agent";
  const source = `/agents/${slug(name)}.png`;
  return (
    <span className="agent-icon" style={{ width: size, height: size }} title={name}>
      {agent && !failed ? (
        <img src={source} alt={name} width={size} height={size} onError={() => setFailed(true)} />
      ) : <span className="agent-icon-fallback" aria-hidden="true">{name.slice(0, 2).toUpperCase()}</span>}
    </span>
  );
}
