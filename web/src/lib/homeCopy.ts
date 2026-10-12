export type HomeHeadlineCopy = {
  headline: string;
  lede: string;
};

export function homeHeadlineCopy(hasFixtures: boolean): HomeHeadlineCopy {
  if (hasFixtures) {
    return {
      headline: "Who wins the next VCT match?",
      lede: "Win chances for every upcoming Tier 1 match, next to what the betting market thinks, and an honest record of how the model has done.",
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
