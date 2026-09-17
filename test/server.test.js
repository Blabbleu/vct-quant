/**
 * Smallest check that fails if the backend breaks: boot it, hit every route.
 *
 *   npm run check          # needs the database: vct init-db && vct update
 */
const assert = require("node:assert/strict");
const { server, ROUTES } = require("../server.js");

async function main() {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    for (const route of Object.keys(ROUTES)) {
      const resp = await fetch(base + route);
      assert.equal(resp.status, 200, `${route} answered ${resp.status}`);
      assert.match(resp.headers.get("content-type"), /application\/json/);
      const body = await resp.json();
      assert.ok(body && (typeof body === "object"), `${route} returned no payload`);
      console.log(`  ${route} ok`);
    }

    const snapshot = await (await fetch(base + "/api/snapshot")).json();
    for (const key of ["coverage", "backtest", "gc", "live", "fixtures", "rankings", "ledger"]) {
      assert.ok(key in snapshot, `snapshot is missing ${key}`);
    }
    assert.ok(snapshot.backtest.log_loss > 0.3 && snapshot.backtest.log_loss < 0.7,
      `implausible log loss ${snapshot.backtest.log_loss}`);

    const page = await fetch(base + "/");
    assert.equal(page.status, 200);
    assert.match(page.headers.get("content-type"), /text\/html/);
    assert.match(await page.text(), /VCT Quant Desk/);
    console.log("  / serves the page");

    assert.equal((await fetch(base + "/nope")).status, 404);
    assert.equal((await fetch(base + "/api/snapshot", { method: "POST" })).status, 405);
    console.log("  404 and read-only 405 ok");
    console.log("all checks passed");
  } finally {
    server.close();
  }
}

main().catch(err => { console.error(err.message); process.exitCode = 1; });
