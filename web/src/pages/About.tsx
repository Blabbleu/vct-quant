import { Chip } from "../components/arena/Chip";
import Panel from "../components/arena/Panel";
import { BIG_GAP_POINTS, COPY, LOW_DATA_MATCHES } from "../lib/constants";
import "./About.css";

/**
 * Plain-language "how it works" guide: prose capped at 68ch, plus a key to
 * the board's colours, shapes and chips (an aside on desktop, below on phone).
 * No eyebrow, no icons, no stat tiles, no example numbers.
 */
export default function About() {
  return (
    <div className="about-page">
      <header className="about-head">
        <h1 className="about-title">How it works</h1>
      </header>
      <div className="about-layout">
        <section className="about-prose">
          <h2>The model</h2>
          <p>Every team has an Elo rating that goes up when it wins and down when it loses, more for convincing results.
            The gap between two ratings turns into a chance of winning the series. It is simple on purpose: over 1,600
            past Tier-1 matches, nothing fancier has beaten it.</p>
          <p className="about-fixed">{COPY.modelBasis}</p>

          <h2>The market</h2>
          <p>The gold number is the Polymarket price, the crowd's view with money behind it. When the market is thin
            (few trades, wide spread) we mark it and leave it in a lighter colour, because the price is mostly noise.</p>
          <p className="about-fixed">{COPY.marketBasis}</p>

          <h2>Reading a forecast</h2>
          <p>60% means that out of ten matches like this one, the favourite should win about six. Upsets are supposed
            to happen; a forecast is judged over many matches, not one.</p>

          <h2>Scoring</h2>
          <p>We use log loss: confident and right scores well, confident and wrong scores badly. A coin flip scores
            0.693. Every forecast is saved before the match, so there is no way to fix the record afterwards.</p>

          <h2>Not betting advice</h2>
          <p>The Edge board tracks model-versus-market gaps on paper to test the model. Nothing here is a
            recommendation to bet.</p>
          <p className="about-fixed">{COPY.edgeDisclaimer}</p>
        </section>

        <aside className="about-aside">
          <Panel cut="l" frame="line">
            <div className="about-key">
              <h2>Reading the board</h2>
              <ul className="about-key-list">
                <li>
                  <span className="about-sw about-sw-model slant" aria-hidden="true" />
                  <span><b>Model</b> &middot; red, solid blocks. The Elo forecast.</span>
                </li>
                <li>
                  <span className="about-sw about-sw-market" aria-hidden="true" />
                  <span><b>Market</b> &middot; gold, triangle notch. Last Polymarket price.</span>
                </li>
                <li>
                  <span className="about-sw about-sw-result" aria-hidden="true" />
                  <span><b>Result</b> &middot; white frame. The winner, and nothing else.</span>
                </li>
              </ul>
              <ul className="about-key-list">
                <li><Chip variant="ghost">AGREE</Chip><span>Model and market within 1 point.</span></li>
                <li><Chip variant="market">BIG GAP</Chip><span>They differ by {BIG_GAP_POINTS} points or more.</span></li>
                <li><Chip variant="ghost">WIDE SPREAD</Chip><span>Thin market; left out of grading.</span></li>
                <li><Chip variant="ghost">LOW DATA</Chip><span>Fewer than {LOW_DATA_MATCHES} rated matches this season.</span></li>
                <li><Chip variant="market">UPSET</Chip><span>The model's favourite lost.</span></li>
                <li><Chip variant="result">HIT</Chip><span>The model's favourite won.</span></li>
              </ul>
              <p className="about-key-note">Gaps read as model minus market for the first-named team.</p>
            </div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
