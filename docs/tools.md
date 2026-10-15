# Contrato das ferramentas

Servidor `capybucks`, transporte stdio, pacote `capybucks-mcp`. Todas as ferramentas são somente leitura (`readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true`, `openWorldHint=true`).

O corpo da ferramenta é um único bloco de texto JSON. Falha de domínio vem com `isError=true` e `ok: false` dentro desse JSON. O processo não usa exceção `ToolError` para esses casos, porque o SDK prefixaria a mensagem.

## Envelope

Sucesso:

```json
{
  "ok": true,
  "tool": "get_history",
  "data": {},
  "provenance": {
    "provider": "yahoo",
    "delayed": true,
    "adjustment": "split_and_dividend",
    "asof": "2026-10-14T23:10:00+00:00",
    "currency": "BRL",
    "timezone": "America/Sao_Paulo"
  },
  "truncation": {
    "rows_total": 252,
    "rows_returned": 100,
    "truncated": true,
    "kept": "most_recent"
  },
  "warnings": [],
  "notice": "Informational data. May be delayed and may come from unofficial sources. Not investment advice. Read-only; this server does not place orders."
}
```

`provenance` só entra quando há dado de mercado. Histórico e cotação preenchem os campos a partir de `df.attrs` ou do `Quote`. Demonstrações, opções, notícias e eventos trazem proveniência fina (`provider`, e o que a chamada sabe) mais o aviso de que o atraso não foi informado pela fonte.

`list_providers` e `check_trading_day` não têm `provenance`.

Erro:

```json
{
  "ok": false,
  "tool": "get_history",
  "error": {
    "code": "symbol_not_found",
    "type": "SymbolNotFound",
    "message": "no price data for 'NOPE' via memory",
    "retryable": false,
    "details": {"symbol": "NOPE", "provider": "memory", "hint": null},
    "next_step": "Ask the user for another symbol. Do not guess a rewrite."
  },
  "warnings": [],
  "notice": "Informational data. May be delayed and may come from unofficial sources. Not investment advice. Read-only; this server does not place orders."
}
```

`NaN`, `NaT` e infinito viram `null`. Datas são ISO 8601 com offset. Um datetime sem fuso é lido como UTC. Preços não são arredondados. Indicadores são arredondados a 6 casas.

Em lote, cada símbolo é um `download` separado. A proveniência fica dentro da série. Falha parcial preenche `errors`. Falha de todos os símbolos devolve `all_symbols_failed`.

## Ferramentas

`provider`, quando existe, é `yahoo`, `coingecko`, `stooq` ou `twelvedata`.

### `list_providers`

Sem parâmetros. Catálogo estático conferido por teste contra o registry real (`requires_key`, `supports_stream`, métodos não implementados). `key_configured` é booleano ou `null`. A resposta inclui o aviso da Yahoo. Não devolve chave.

### `get_history`

`symbols` (texto ou lista, 1 a 10), `period` padrão `1mo` (`1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `max`, `ytd`), `interval` padrão `1d`, `start`, `end`, `auto_adjust` padrão true, `provider`, `view` `rows` ou `summary`, `max_rows` padrão 100 (teto 500), `use_cache` padrão true.

Um símbolo: `{symbol, columns, rows}` ou o resumo. Vários: `{series, errors}`.

`view=summary` calcula `count`, `first_date`, `last_date`, `first_close`, `last_close`, `change_pct`, `high_max`, `low_min`, `avg_volume` e as 5 últimas linhas a partir da coluna `Close` (ajustada quando `auto_adjust` é true). O aviso diz que a conta é do servidor.

Intervalos aceitos dependem do provedor e copiam a biblioteca. Símbolo com `-` sem `provider` gera aviso: a biblioteca trata hífen como cripto (`BRK-B`). Volume CoinGecko sai `null`.

### `get_quote`

`symbol`, `provider`. Retorno: `symbol`, `price`, `timestamp`, `currency`, `delayed`, `quote_kind`.

`quote_kind` é `last_daily_bar` na Yahoo e no CoinGecko, e `provider_quote` na Twelve Data. O aviso de cotação entra sempre.

### `get_financials`

`symbol`, `statement` `income` | `balance` | `cashflow`, `frequency` `annual` | `quarterly`, `provider`, `items`, `max_periods` padrão 4 (teto 8).

Mapa: `financials`, `quarterly_financials`, `balance_sheet`, `quarterly_balance_sheet`, `cashflow`, `quarterly_cashflow`.

Retorno: `{statement, frequency, periods, items}`. Itens todos nulos saem. O filtro `items` é sem diferenciar maiúsculas. Teto de 60 itens. Os períodos mais recentes permanecem. Demonstração vazia é `provider_error`, não uma tabela de zeros. CoinGecko e Stooq devolvem `unsupported_capability`.

### `get_dividends_and_splits`

`symbol`, `kind` `both` | `dividends` | `splits`, `since`, `max_rows`, `provider`.

Retorno: `{dividends: [{date, amount}], splits: [{date, ratio}]}`. Lista vazia é sucesso.

### `get_option_expirations`

`symbol`, `provider`. Retorno: `{expirations: ["YYYY-MM-DD", ...]}`.

### `get_option_chain`

`symbol`, `expiration` (padrão o próximo vencimento), `side` `both` | `calls` | `puts`, `near_money` padrão true, `strike_min`, `strike_max`, `max_rows` padrão 50 (teto 100 por lado), `provider`.

`near_money` busca o último fechamento diário no mesmo provedor (período `5d`) e fica na faixa de ±15% desse preço. Janela vazia cai para os strikes mais próximos, com aviso. Ordenação por strike. Campos: `contract_symbol`, `strike`, `last_price`, `bid`, `ask`, `volume`, `open_interest`, `implied_volatility`, `in_the_money`. Só a Yahoo implementa a cadeia hoje.

### `get_news`

`symbol`, `max_items` padrão 10 (teto 20), `provider`.

Retorno: `{items: [{title, publisher, link, published_at}], untrusted_text: true}` mais aviso de texto não confiável.

### `compute_indicators`

`symbol`, `indicators` padrão `sma` e `rsi` (`sma`, `ema`, `rsi`, `macd`, `bollinger`, `atr`, `vwap`), `period` padrão `6mo`, `interval` padrão `1d`, `provider`, `window` 20, `rsi_window` 14, `atr_window` 14, `macd_fast` 12, `macd_slow` 26, `macd_signal` 9, `bands_std` 2, `last_n` padrão 30 (teto 200).

Usa `capybucks.ta` sobre o histórico. Não usa `enrich`. Janelas de 2 a 400. `macd_fast` tem de ser menor que `macd_slow`. Formato colunar `{columns, rows}` com as últimas `last_n` linhas. Aquecimento fica `null`, com aviso da janela mínima. VWAP no CoinGecko é nulo.

### `check_trading_day`

`symbol`, `date` (padrão hoje, no fuso do calendário), `calendar` (código do `exchange_calendars`).

`.SA` seleciona `BVMF`, `.L` seleciona `XLON`, o resto `XNYS`, salvo `calendar` explícito. Retorno: `{calendar, date, is_session}`. O aviso diz que isso não informa se o pregão está aberto agora. Calendário desconhecido é `invalid_argument`.

## Erros

| Exceção | `code` | `retryable` | Próximo passo |
|---|---|---|---|
| `SymbolNotFound` | `symbol_not_found` | não | Se houver `hint`, repetir com ele. Senão, pedir outro símbolo |
| `MissingAPIKey` de provedor com chave (hoje só a Twelve Data, `CAPYBUCKS_TWELVEDATA_KEY`) | `missing_api_key` | não | Configurar essa variável ou `~/.capybucks.toml`. Não pedir a chave no chat |
| `MissingAPIKey` da Yahoo, do Stooq ou do CoinGecko (HTTP 401) | `provider_error` | não | Acesso negado. A Yahoo não é API oficial e não usa chave. Tentar de novo mais tarde |
| `RateLimitError` e cooldown | `rate_limited` | sim | Esperar `retry_after_seconds`. Não trocar de provedor. HTTP 403 cai aqui e a biblioteca tenta de novo até 3 vezes |
| `ProviderError`, inclusive JSON inválido com HTTP 200 | `provider_error` | se a mensagem citar HTTP 5, bot-check ou timeout | Ler a mensagem. HTTP 404 permanece neste código |
| `ProviderNotFound` | `unknown_provider` | não | Usar um nome da lista |
| `NoProviderError` | `no_provider` | não | Não há provedor para o ativo e o intervalo. Símbolo com `/` nem chega aqui: a validação devolve `invalid_argument` |
| `MultiDownloadError` / falha total do lote | `all_symbols_failed` | não | Ler o mapa por símbolo |
| `StreamingNotSupportedError` | `streaming_unsupported` | não | Não há ferramenta de stream |
| `NotImplementedError` | `unsupported_capability` | não | Outro provedor, explícito, ou aceitar a lacuna |
| `ValueError` | `invalid_argument` | não | Corrigir o argumento |
| `ImportError` | `missing_extra` | não | Reinstalar. O extra `calendars` já é dependência |
| `httpx.HTTPError`, `TimeoutError` | `network_error` | sim | Tentar de novo mais tarde |
| Qualquer outra | `internal_error` | não | A resposta traz `correlation_id` e a mensagem `internal error`. O traceback fica no stderr |

Toda mensagem passa pelo scrubber. Resposta de erro que usou a Yahoo inclui `YAHOO_WARNING`.
