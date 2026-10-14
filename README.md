# capybucks-mcp

Servidor MCP por stdio, somente leitura, para a biblioteca [capybucks](https://github.com/witmondcal-maker/capybucks) (PyPI `capybucks` 0.0.1). O comando é `capybucks-mcp`. O pacote PyPI pretendido é `capybucks-mcp`.

Read-only stdio MCP server for the [capybucks](https://github.com/witmondcal-maker/capybucks) library (PyPI `capybucks` 0.0.1). The command is `capybucks-mcp`. The intended PyPI package is `capybucks-mcp`.

**Este pacote ainda não foi publicado no PyPI e não foi enviado a nenhum marketplace.** Os passos estão em [docs/publishing.md](docs/publishing.md).

**This package has not been published to PyPI and has not been submitted to any marketplace.** The steps are in [docs/publishing.md](docs/publishing.md).

---

## Português

### O que é

Dez ferramentas de dados de mercado: histórico OHLCV, cotação, demonstrações, dividendos e splits, opções, notícias, indicadores e dia de pregão. Cada resposta é JSON com `provenance` (quando há dado de mercado), `truncation`, `warnings` e `notice`.

Não executa ordens, não lê contas e não recomenda investimento. A Yahoo Finance continua sendo a fonte padrão de ações, com aviso visível em toda resposta que a usa. Os endpoints da Yahoo (`query1.finance.yahoo.com`) não são uma API oficial, podem mudar ou parar sem aviso, e os termos da Yahoo restringem coleta automatizada. Não redistribua dados dos provedores.

A licença MIT cobre só este software. Os dados seguem os termos de cada provedor.

### Aviso em toda resposta

> Informational data. May be delayed and may come from unofficial sources. Not investment advice. Read-only; this server does not place orders.

### Pré-requisitos

- Python 3.11 ou mais novo
- [uv](https://docs.astral.sh/uv/) (o cliente MCP vai chamar `uvx` depois da publicação)

A primeira execução de `uvx` baixa `pandas` e `pyarrow`, dependências da biblioteca. Isso pode passar do tempo de partida do cliente. Depois da publicação, pré-aqueça o cache:

```bash
uvx capybucks-mcp --version
```

`--version` imprime a versão e sai. Não abre o stdio. A partida a frio com cache vazio do `uvx` não foi medida: o pacote ainda não está no PyPI. Com o ambiente deste repositório já sincronizado, `uv run capybucks-mcp --version` levou cerca de 0,9 s (2026-10-14).

### Instalar e rodar a partir deste repositório

```bash
uv sync --all-groups
uv run capybucks-mcp
```

O processo fala JSON-RPC no stdout. Logs vão para o stderr, com valores de chave removidos.

Depois da publicação no PyPI (não feita nesta entrega):

```bash
uvx capybucks-mcp
```

O plugin do marketplace, quando existir no repositório separado `capybucks-plugin`, deve fixar a versão (`uvx capybucks-mcp==0.1.0`). Esse pin não mora neste repositório.

### Chave

A única chave de provedor é a da Twelve Data:

```bash
export CAPYBUCKS_TWELVEDATA_KEY="..."
```

A biblioteca também lê `~/.capybucks.toml` (`[keys]`, chave `twelvedata`). A variável de ambiente ganha do arquivo. O servidor nunca devolve, registra ou ecoa a chave. `list_providers` só diz se ela está configurada.

Na partida, um valor vazio ou o placeholder não resolvido `${...}` em qualquer `CAPYBUCKS_*` é removido do ambiente do processo. Assim a biblioteca cai no arquivo toml e, se não houver chave, o erro é `missing_api_key`.

Não defina `CAPYBUCKS_NO_RATELIMIT`. A biblioteca reserva essa variável para testes.

### Outras variáveis

| Variável | Efeito |
|---|---|
| `CAPYBUCKS_CACHE_DIR` | Pasta do cache parquet de histórico (padrão `~/.cache/capybucks`) |
| `CAPYBUCKS_MCP_MAX_ROWS` | Teto e padrão de linhas de histórico, no máximo 500 |
| `CAPYBUCKS_MCP_TTL_SECONDS` | `0` desliga o cache em memória. Um número positivo substitui todos os TTLs |
| `CAPYBUCKS_MCP_LOG_LEVEL` | Nível de log no stderr (`WARNING` por padrão) |
| `CAPYBUCKS_MCP_TEST_MEMORY` | Só testes. Não é fonte de dados pública |

TTLs em memória (plano, não alterados): cotação 30 s, notícias 300 s, opções 60 s, demonstrações e eventos corporativos 6 h. Histórico usa o cache da biblioteca, sem TTL. Depois de `RateLimitError`, o provedor fica 30 s em cooldown.

### Ferramentas

| Ferramenta | Uso |
|---|---|
| `list_providers` | Provedores, capacidades e se a chave está configurada |
| `get_history` | OHLCV, até 10 símbolos, uma chamada por símbolo |
| `get_quote` | Última barra diária (Yahoo e CoinGecko) ou cotação da Twelve Data |
| `get_financials` | DRE, balanço ou fluxo de caixa |
| `get_dividends_and_splits` | Dividendos e desdobramentos |
| `get_option_expirations` | Vencimentos de opções |
| `get_option_chain` | Cadeia, com janela perto do dinheiro por padrão |
| `get_news` | Manchetes. Texto de terceiros (`untrusted_text`) |
| `compute_indicators` | SMA, EMA, RSI, MACD, Bollinger, ATR, VWAP |
| `check_trading_day` | Se a data é dia de pregão. Não diz se o mercado está aberto agora |

Contrato, erros e proveniência: [docs/tools.md](docs/tools.md). Segurança e avisos longos: [docs/security.md](docs/security.md). Achados da fase 0: [docs/phase0.md](docs/phase0.md).

### Proveniência

Quando o dado vem de mercado, a resposta traz `provider`, `delayed`, `adjustment`, `asof` e, quando a fonte informa, `currency` e `timezone`. Cite esses campos. `delayed: true` não é tempo real. Demonstrações, opções e notícias não trazem atraso da biblioteca: o envelope avisa que o atraso não foi informado.

Símbolos com hífen (`BRK-B`) são tratados como cripto pela biblioteca. Para a ação, passe `provider=yahoo`. Ações brasileiras na Yahoo usam o sufixo `.SA` (`PETR4.SA`). Um HTTP 404 da Yahoo chega como `provider_error`, sem a dica `.SA`. Veja [docs/phase0.md](docs/phase0.md).

### Hosts de saída

Somente `query1.finance.yahoo.com`, `api.coingecko.com`, `api.twelvedata.com` e `stooq.com`. Sem telemetria. A única escrita local é o cache parquet.

### Desenvolvimento

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest
uv run pip-audit
```

`pytest` ignora o marcador `live`. O workflow semanal `.github/workflows/smoke.yml` roda `pytest -m live` contra provedores reais.

### Problemas

Abra uma issue em <https://github.com/witmondcal-maker/capybucks-mcp/issues>. Não cole chaves. Vulnerabilidades: [SECURITY.md](SECURITY.md).

---

## English

### What it is

Ten market-data tools: OHLCV history, quote, financial statements, dividends and splits, options, news, indicators, and trading-day checks. Every response is JSON with `provenance` (when the payload is market data), `truncation`, `warnings`, and `notice`.

It does not place orders, read brokerage accounts, or give investment advice. Yahoo Finance stays the default equity source, with a visible warning on every response that uses it. Yahoo's endpoints (`query1.finance.yahoo.com`) are not an official API. They can change or stop without notice, and Yahoo's terms restrict automated collection. Do not redistribute provider data.

The MIT license covers this software only. Market data follows each provider's terms.

### Notice on every response

> Informational data. May be delayed and may come from unofficial sources. Not investment advice. Read-only; this server does not place orders.

### Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) (an MCP client will call `uvx` after publication)

The first `uvx` run downloads `pandas` and `pyarrow`, which the library requires. That download can exceed an MCP client's startup timeout. After publication, warm the cache:

```bash
uvx capybucks-mcp --version
```

`--version` prints the version and exits. It does not start stdio. A cold `uvx` start against an empty cache was not measured, because the package is not on PyPI. In this repository's already synced environment, `uv run capybucks-mcp --version` took about 0.9 s (2026-10-14).

### Install and run from this repository

```bash
uv sync --all-groups
uv run capybucks-mcp
```

The process speaks JSON-RPC on stdout. Logs go to stderr, with key values removed.

After a PyPI release (not done in this delivery):

```bash
uvx capybucks-mcp
```

The marketplace plugin, when it exists in the separate `capybucks-plugin` repository, should pin the version (`uvx capybucks-mcp==0.1.0`). That pin does not live in this repository.

### API key

The only provider key is Twelve Data:

```bash
export CAPYBUCKS_TWELVEDATA_KEY="..."
```

The library also reads `~/.capybucks.toml` (`[keys]`, key `twelvedata`). The environment variable wins. The server never returns, logs, or echoes the key. `list_providers` only reports whether it is configured.

At startup, an empty value or an unresolved `${...}` placeholder on any `CAPYBUCKS_*` variable is removed from the process environment. The library then falls through to the toml file and, if no key exists, the error is `missing_api_key`.

Do not set `CAPYBUCKS_NO_RATELIMIT`. The library reserves that variable for tests.

### Other variables

| Variable | Effect |
|---|---|
| `CAPYBUCKS_CACHE_DIR` | Parquet history cache directory (default `~/.cache/capybucks`) |
| `CAPYBUCKS_MCP_MAX_ROWS` | History row default and ceiling, absolute cap 500 |
| `CAPYBUCKS_MCP_TTL_SECONDS` | `0` disables the in-memory cache. A positive number overrides every TTL |
| `CAPYBUCKS_MCP_LOG_LEVEL` | stderr log level (`WARNING` by default) |
| `CAPYBUCKS_MCP_TEST_MEMORY` | Tests only. Not a public data source |

In-memory TTLs (plan defaults, unchanged): quote 30 s, news 300 s, options 60 s, statements and corporate actions 6 h. History uses the library cache, which has no TTL. After a `RateLimitError`, that provider is in cooldown for 30 s.

### Tools

| Tool | Use |
|---|---|
| `list_providers` | Providers, capabilities, and whether the key is configured |
| `get_history` | OHLCV, up to 10 symbols, one download per symbol |
| `get_quote` | Last daily bar (Yahoo and CoinGecko) or the Twelve Data quote |
| `get_financials` | Income, balance sheet, or cash flow |
| `get_dividends_and_splits` | Dividends and splits |
| `get_option_expirations` | Option expiration dates |
| `get_option_chain` | Chain, near-the-money window by default |
| `get_news` | Headlines. Third-party text (`untrusted_text`) |
| `compute_indicators` | SMA, EMA, RSI, MACD, Bollinger, ATR, VWAP |
| `check_trading_day` | Whether a date is a session. It does not say whether the market is open now |

Contract, errors, and provenance: [docs/tools.md](docs/tools.md). Security and the long warnings: [docs/security.md](docs/security.md). Phase 0 findings: [docs/phase0.md](docs/phase0.md).

### Provenance

When the payload is market data, the response includes `provider`, `delayed`, `adjustment`, `asof`, and, when the source reports them, `currency` and `timezone`. Cite those fields. `delayed: true` is not real time. Statements, options, and news do not carry a library delay: the envelope warns that delay was not reported.

Hyphenated symbols (`BRK-B`) are inferred as crypto by the library. For the equity, pass `provider=yahoo`. Brazilian equities on Yahoo use the `.SA` suffix (`PETR4.SA`). An HTTP 404 from Yahoo arrives as `provider_error`, without the `.SA` hint. See [docs/phase0.md](docs/phase0.md).

### Egress hosts

Only `query1.finance.yahoo.com`, `api.coingecko.com`, `api.twelvedata.com`, and `stooq.com`. No telemetry. The only local write is the parquet cache.

### Development

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest
uv run pip-audit
```

`pytest` skips the `live` marker. The weekly workflow `.github/workflows/smoke.yml` runs `pytest -m live` against real providers.

### Issues

Open an issue at <https://github.com/witmondcal-maker/capybucks-mcp/issues>. Do not paste keys. Vulnerabilities: [SECURITY.md](SECURITY.md).
