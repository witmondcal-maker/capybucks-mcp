# Changelog

## 0.1.0 — unreleased

First read-only stdio MCP server for capybucks 0.0.1. Not published to PyPI.

- Tools: `list_providers`, `get_history`, `get_quote`, `get_financials`, `get_dividends_and_splits`, `get_option_expirations`, `get_option_chain`, `get_news`, `compute_indicators`, `check_trading_day`.
- JSON envelopes with provenance, truncation, warnings, and a fixed notice. Typed errors. API keys only through the environment, scrubbed from responses and stderr.
- Yahoo remains the default equity source, with a visible unofficial-API warning.
- HTTP 404 from Yahoo stays `provider_error`. Unmapped CoinGecko ids warn instead of being rewritten.
- Offline tests, a `tools/list` snapshot, a stdio protocol test, and a key-leak test. CI workflows for tests, weekly live smoke, weekly library compatibility, and a release publish job that is not triggered by this change.
