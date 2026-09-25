import { PageHead } from "../components/ui";

export default function About() {
  return (
    <>
      <PageHead eyebrow="Two-minute guide" title="How it works" />
      <section className="panel pad prose">
        <h2>The model</h2>
        <p>Every team has an Elo rating that goes up when it wins and down when it loses, more for convincing results.
          The gap between two ratings turns into a chance of winning the series. It is simple on purpose: over 1,600 past
          Tier-1 matches, nothing fancier has beaten it.</p>
        <h2>The market</h2>
        <p>The orange number is the Polymarket price, the crowd's view with money behind it. When the market is thin
          (few trades, wide spread) we fade it out, because the price is mostly noise.</p>
        <h2>Reading a forecast</h2>
        <p>60% means that out of ten matches like this one, the favourite should win about six. Upsets are supposed to
          happen; a forecast is judged over many matches, not one.</p>
        <h2>Scoring</h2>
        <p>We use log loss: confident and right scores well, confident and wrong scores badly. A coin flip scores 0.693.
          Every forecast is saved before the match, so there is no way to fix the record afterwards.</p>
        <h2>Not betting advice</h2>
        <p>The edge board tracks model-vs-market gaps on paper to test the model. Nothing here is a recommendation to bet.</p>
      </section>
    </>
  );
}
