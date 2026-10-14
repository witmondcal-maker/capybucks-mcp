# Fase 0 — decisões e verificação no código real

Data: 2026-10-14. Escopo: este repositório (`capybucks-mcp`). O repositório do plugin e o marketplace ficam de fora. Nada foi publicado no PyPI.

A biblioteca lida foi `capybucks` 0.0.1 (código em `https://github.com/witmondcal-maker/capybucks` e o wheel instalado). O SDK lido foi `mcp` 2.3.0.

## Decisões do Ricardo

| Pergunta | Decisão |
|---|---|
| Licença | MIT, com a nota de que a licença cobre o software e não os dados |
| Autor | Ricardo Margalho &lt;ricardo@penarede.com.br&gt; no `pyproject.toml` e nos commits |
| Yahoo | Continua fonte padrão de ações, com aviso visível (`YAHOO_WARNING`) |
| Repositórios | Este repo é só o servidor. O plugin (`capybucks-plugin`) não é implementado aqui |

TTLs e cooldown (Q8 do plano, sem alteração): cotação 30 s, notícias 300 s, opções 60 s, demonstrações e eventos 6 h, cooldown 30 s depois de `RateLimitError`. `CAPYBUCKS_MCP_TTL_SECONDS=0` desliga o cache em memória. Um valor positivo substitui todos os TTLs.

## SDK (`mcp` 2.3)

- Import: `from mcp.server.mcpserver import MCPServer`. `FastMCP` não é a API 2.x usada aqui.
- Transporte: `MCPServer(...).run(transport="stdio")`.
- Anotações: `read_only_hint`, `destructive_hint=False`, `idempotent_hint`, `open_world_hint`, mais `title`.
- `structured_output=False`. O corpo é JSON texto.
- Erro de ferramenta: devolver `mcp.types.CallToolResult(..., is_error=True)`. Levantar `ToolError` prefixa a mensagem com "Error executing tool", então o servidor não usa essa exceção para o envelope.
- O atributo Python é `is_error` (no fio, `isError`).
- Cliente de teste: `mcp.client.stdio.stdio_client`. O ambiente do subprocesso herda o ambiente padrão do SDK e recebe as variáveis extras do teste.
- `functools.wraps` faz o schema seguir a assinatura original da ferramenta.

## HTTP 404 da Yahoo fica `provider_error`

`capybucks.core.http._raise_status` mapeia 429 e 403 para `RateLimitError`, 401 para `MissingAPIKey`, e qualquer outro status ≥ 400, inclusive 404, para `ProviderError`. Isso acontece antes de o parser do gráfico da Yahoo poder levantar `SymbolNotFound`.

Consulta direta (curl, 2026-10-14, sem passar pela biblioteca), em `query1.finance.yahoo.com`:

- `NOTAREALTICKERXYZ` responde HTTP 404 com JSON `chart.result = null` e `chart.error.code = "Not Found"`.
- `PETR4` (sem `.SA`) responde o mesmo HTTP 404.
- `PETR4.SA` responde HTTP 200, moeda BRL.

Consequência: a dica `PETR4.SA` de `SymbolNotFound` não aparece nesse 404. O MCP não remapeia. O teste live `tests/live/test_live.py` exige `provider_error` com "404" para um símbolo inválido e falha de propósito se a biblioteca passar a levantar `SymbolNotFound`. A dica `.SA` continua quando a biblioteca realmente levanta `SymbolNotFound` (por exemplo o `MemoryProvider`, ou um HTTP 200 cujo corpo do gráfico traz erro).

Issue recomendada na biblioteca, não aberta: mapear o 404 do gráfico da Yahoo para `SymbolNotFound` dentro do provedor, para o hint de B3 voltar a aparecer. Até lá, quem pedir `PETR4` precisa informar o sufixo.

## CoinGecko: id não mapeado pode ser outro ativo

`to_coingecko_id` só mapeia BTC, ETH e SOL (e as formas `-USD` / `USD` que a biblioteca conhece). O resto vira `symbol.lower()`.

Consulta direta (2026-10-14):

- `GET /coins/dogecoin/ohlc` devolve preço na ordem de 0,084.
- `GET /coins/doge/ohlc` responde HTTP 200 com preço na ordem de 4,6e-5. É outro ativo, não um 404.

O MCP avisa (`UNMAPPED_COINGECKO`) quando o provedor resolvido é `coingecko` e o símbolo está fora de `MAPPED_COINGECKO_SYMBOLS`. Não inventa `SymbolNotFound`. O teste de paridade compara o conjunto mapeado com `to_coingecko_id` e falha se a biblioteca passar a mapear DOGE, XRP, ADA ou `SOLUSD`.

Volume do CoinGecko: a biblioteca grava `0.0` quando o volume é `None`. O MCP devolve `null` e avisa que a fonte não informou volume. VWAP nesse caso também fica nulo.

## Placeholder `${VAR}`

Na partida, `normalize_process_env` apaga `CAPYBUCKS_*` vazio ou que case `^\$\{[^}]+\}$`. Um placeholder não resolvido pelo cliente não é enviado como chave. A biblioteca pode então ler `~/.capybucks.toml`. Sem chave, o erro é `missing_api_key`.

## Partida

`uvx` a frio não foi medido: o pacote não está no PyPI. Proxy quente, neste ambiente já sincronizado, em 2026-10-14: `uv run capybucks-mcp --version` imprimiu `0.1.0` em cerca de 0,9 s e não abriu o stdio. O README pede o pré-aquecimento `uvx capybucks-mcp --version` depois da publicação, porque `pandas` e `pyarrow` são dependências duras da biblioteca.

## Fora deste repositório

- Plugin, skills, `mcp.json` e submissão ao marketplace: repositório `capybucks-plugin`, não criado aqui.
- O pin `capybucks-mcp==0.1.0` entra nesse `mcp.json` só depois do PyPI.
- Nenhuma issue foi aberta em `witmondcal-maker/capybucks`.
