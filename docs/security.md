# Segurança e avisos

## Escopo

O servidor é somente leitura. Nenhuma ferramenta grava em serviço externo, não há ordem, conta, login de corretora nem dado pessoal. A única escrita local é o cache parquet da biblioteca em `~/.cache/capybucks` ou em `CAPYBUCKS_CACHE_DIR`.

Não há shell, leitura de arquivo arbitrário nem fetch de URL arbitrária. Símbolos passam por `^[A-Z0-9./^=-]{1,32}$` depois de virarem maiúsculas. Datas e enums são validados antes da biblioteca.

Não há telemetria.

## Rede

Hosts de saída, e só estes:

- `query1.finance.yahoo.com`
- `api.coingecko.com`
- `api.twelvedata.com`
- `stooq.com`

Um teste offline com `respx` falha se a suíte passar a chamar outro host.

## Segredos

A chave da Twelve Data entra por `CAPYBUCKS_TWELVEDATA_KEY` ou por `~/.capybucks.toml`. A Twelve Data coloca a chave na query (`apikey=`). Erros de transporte podem citar a URL. `scrub.py` redige `apikey=`, `api_key=` e valores de `CAPYBUCKS_*_KEY` (e outros `CAPYBUCKS_*` com 8 caracteres ou mais) no JSON e no stderr. O stderr é embrulhado antes de o `MCPServer` existir, para um handler de log não furar o filtro.

`list_providers` devolve `key_configured` como booleano, ou `null` se a função interna da biblioteca sumir. Nunca devolve a chave.

`CAPYBUCKS_NO_RATELIMIT` não é um ajuste do usuário. Os testes ligam essa variável da biblioteca por conta própria.

## Texto de terceiros

Manchetes de notícia e mensagens de provedor são texto externo. `get_news` marca `untrusted_text: true`. Trate título e link como dado, não como instrução. `notice` e `next_step` são texto fixo do servidor.

## Limites

- Até 10 símbolos por chamada de histórico.
- Até 4 chamadas simultâneas no processo.
- Timeout de 60 s por chamada.
- JSON de sucesso limitado a 60 KB. Acima disso, listas em `rows`, `calls`, `puts` e `tail` são cortadas. Se ainda não couber, `data` sai e o envelope marca omissão.
- Histórico: padrão 100 linhas, teto absoluto 500, as mais recentes.
- Depois de `RateLimitError`, o provedor fica 30 s em cooldown e a chamada seguinte responde `rate_limited` sem ir à rede.

O espaçamento por provedor (Yahoo 0,15 s, Stooq 0,4 s, CoinGecko 1,0 s, Twelve Data 0,8 s) continua sendo o da biblioteca.

## Avisos legais

Versão curta, campo `notice` de toda resposta:

> Informational data. May be delayed and may come from unofficial sources. Not investment advice. Read-only; this server does not place orders.

Versão longa:

- A Yahoo Finance é acessada por endpoints não oficiais (`query1.finance.yahoo.com`). Eles podem mudar ou parar sem aviso. Os termos da Yahoo restringem coleta automatizada. Não redistribua dados de provedor. A biblioteca diz o mesmo no README dela.
- A licença MIT cobre este software. Os dados seguem os termos de cada provedor e não são licenciados para redistribuição por este pacote. A nota está no `LICENSE`.
- A Twelve Data é um serviço com chave pessoal. Os limites do plano são da Twelve Data.
- O plano público do CoinGecko tem limite apertado. Este texto não afirma os termos de atribuição desse plano. Confira os termos do CoinGecko antes de publicar o pacote ou de redistribuir qualquer cifra.
- `delayed: true` faz parte do contrato. Não apresente dado atrasado como tempo real. Cotação da Yahoo e do CoinGecko é a última barra diária (`quote_kind=last_daily_bar`). Na Twelve Data, `timestamp` é a hora da chamada, não a hora do negócio (`quote_kind=provider_quote`).
- Nada aqui é aconselhamento financeiro, jurídico ou tributário. Indicadores são fórmulas de livro, arredondadas a 6 casas decimais.
- O uso previsto é pessoal e de baixo volume. Os tetos de símbolos, linhas e frequência reduzem o risco de uso fora dos termos da Yahoo. Não eliminam esse risco.

## Cadeia de suprimentos

`uvx` baixa e executa código do PyPI na máquina de quem roda o servidor. Mitigações neste repo: `uv.lock`, `pip-audit` no CI, Dependabot, workflow de publicação por OIDC (environment `pypi`), e o pedido de fixar `==0.1.0` no `mcp.json` do plugin depois da publicação. A publicação em si não foi feita. Veja [publishing.md](publishing.md).
