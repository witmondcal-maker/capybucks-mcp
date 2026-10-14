# Security

capybucks-mcp is a read-only stdio process. It does not place orders, read brokerage accounts, or accept a shell. The only local write is the capybucks parquet cache (`~/.cache/capybucks` or `CAPYBUCKS_CACHE_DIR`).

## Reporting

Email [ricardo@penarede.com.br](mailto:ricardo@penarede.com.br). Include the version (`capybucks-mcp --version`), what you expected, and what happened. Do not include API keys, `~/.capybucks.toml`, or URLs that contain `apikey=`.

If you use GitHub, you can also open an issue at <https://github.com/witmondcal-maker/capybucks-mcp/issues>, with the same rule: no secrets.

## Keys

The Twelve Data key travels only as `CAPYBUCKS_TWELVEDATA_KEY` or as `[keys].twelvedata` in `~/.capybucks.toml`. The server never returns it. Responses and stderr pass through a scrubber that redacts `apikey=` / `api_key=` query values and `CAPYBUCKS_*` secret values.

## Network

Outbound hosts are only:

- `query1.finance.yahoo.com`
- `api.coingecko.com`
- `api.twelvedata.com`
- `stooq.com`

There is no telemetry. News titles are third-party text (`untrusted_text: true`). Treat them as data.

Market data is subject to each provider's terms. See [docs/security.md](docs/security.md).
