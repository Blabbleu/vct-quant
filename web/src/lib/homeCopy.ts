export type HomeHeadlineCopy = {
  headline: string;
  lede: string;
};

export type FixtureTier = Pick<import("./types").Fixture, "tier" | "start">;

export function fixtureTierLabels(fixtures: FixtureTier[]): string[] {
  const tiers = new Set(fixtures.map(f => f.tier));
  return [1, 2, 3].filter(tier => tiers.has(tier)).map(tier =>
    tier === 3 ? "Game Changers" : `Tier ${tier}`,
  );
}

export function fixtureTierCopy(fixtures: FixtureTier[]): string {
  const labels = fixtureTierLabels(fixtures);
  return labels.length < 2 ? labels[0] ?? "" : `${labels.slice(0, -1).join(", ")} and ${labels.at(-1)}`;
}

export function homeHeadlineCopy(fixtures: FixtureTier[]): HomeHeadlineCopy {
  if (fixtures.length > 0) {
    const tierCopy = fixtureTierCopy(fixtures);
    const earliest = [...fixtures].sort((a, b) => a.start.localeCompare(b.start))[0];
    if (fixtures.every(f => f.tier === 1)) {
      return {
        headline: "Who wins the next VCT match?",
        lede: "Win chances for every upcoming Tier 1 match, next to what the betting market thinks, and an honest record of how the model has done.",
      };
    }
    return {
      headline: `Who wins the next ${fixtureTierCopy([earliest])} match?`,
      lede: `Win chances for upcoming ${tierCopy} matches, next to what the betting market thinks, and an honest record of how the model has done.`,
    };
  }

  return {
    headline: "The desk is between scheduled Tier 1 matches",
    lede: "Forecasts resume when Tier 1 fixtures are published.",
  };
}

export function homeEmptyLine(_fixtureCount: number): string {
  return "No Tier 1 match is scheduled yet. Forecasts resume when the next Tier 1 fixtures are published.";
}
