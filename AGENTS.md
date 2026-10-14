# Agents

Short rules for changes in this repository. The library rules live in [capybucks](https://github.com/witmondcal-maker/capybucks).

- This package is a read-only MCP client of capybucks. Do not add orders, accounts, streaming, charts, or a backtester.
- Call `capybucks.async_api` (`download`, `AsyncTicker`). Do not call the sync wrappers from the server.
- One symbol per `download`. A batch frame drops per-symbol provenance.
- Do not stitch candles from two providers into one series, and do not add an automatic provider fallback.
- Do not remap Yahoo HTTP 404 to `SymbolNotFound`. The library raises `ProviderError` before the chart parser runs. The B3 `.SA` hint appears only when the library raises `SymbolNotFound`.
- Do not invent a CoinGecko id. Warn when the symbol is outside the mapped set (BTC, ETH, SOL and the forms listed in `catalog.py`).
- Yahoo stays the default equity source. Keep `YAHOO_WARNING` on responses that use it.
- Never log, return, or echo an API key. New text that leaves the process goes through `scrub`.
- Do not expose `CAPYBUCKS_NO_RATELIMIT` as a user setting.
- `CAPYBUCKS_MCP_TEST_MEMORY` is for tests. It is not a public data source.
- Prices are not rounded. Indicators round to 6 decimals.
- Default `pytest` stays offline (`-m "not live"`). A `tools/list` change updates `tests/contract/snapshots/tools.json` only with `UPDATE_SNAPSHOT=1` in the same change.
- Do not publish to PyPI or submit a marketplace plugin from this repository unless Ricardo asks for that release. Publishing steps are in `docs/publishing.md`.
