# Publicação

Nada disto foi executado. Não publique a partir de um agente sem um pedido explícito de release. Não submeta o marketplace a partir deste repositório: o plugin mora em `capybucks-plugin`, que este plano deixa para outro repo.

Versão deste código: `0.1.0` em `pyproject.toml`. Nome no PyPI: `capybucks-mcp`. Em 2026-10-14 o plano registrou que esse nome respondia HTTP 404 no PyPI. Confira de novo imediatamente antes de publicar.

## 1. Pending publisher (manual, Ricardo)

No PyPI e, primeiro, no TestPyPI:

1. Conta com permissão de criar o projeto `capybucks-mcp` (ou o projeto vazio, se a conta exigir criá-lo antes).
2. Publishing → add a new pending publisher.
3. Owner: `witmondcal-maker`. Repository: `capybucks-mcp`. Workflow: `publish.yml`. Environment: `pypi`.

O workflow `.github/workflows/publish.yml` só dispara em **release publicada** (`release: types: [published]`). Ele pede `id-token: write`, usa o environment `pypi`, confere se a tag sem o prefixo `v` é igual à versão do `pyproject.toml`, roda `pytest`, `uv build` e `pypa/gh-action-pypi-publish`.

No GitHub, o environment `pypi` precisa existir e permitir o OIDC desse repositório. Sem o pending publisher, o job falha na hora de enviar.

## 2. TestPyPI primeiro

1. Confirme que `main` contém o commit que deve sair como `0.1.0`.
2. Crie a tag `v0.1.0` apontando para esse commit. A tag tem de coincidir com `project.version`.
3. Publique um GitHub Release a partir dessa tag. Isso dispara `publish.yml`.
4. Para o TestPyPI, o pending publisher e o environment precisam apontar para o TestPyPI nessa primeira vez (troque o destino do action, ou use um environment separado, antes de apontar para o PyPI de produção). O arquivo atual usa o destino padrão do `gh-action-pypi-publish`, que é o PyPI de produção. Na primeira vez, passe `repository-url: https://test.pypi.org/legacy/` no step de publish, rode, e só então remova essa URL.
5. Verifique:

```bash
uvx --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    capybucks-mcp --version
```

O `--extra-index-url` é necessário porque `capybucks` e `mcp` estão no PyPI, não no TestPyPI.

## 3. PyPI

Quando o TestPyPI responder `--version` com `0.1.0`:

1. Restaure o step de publish para o PyPI de produção (sem `repository-url` de teste).
2. Confirme o pending publisher no PyPI de produção, environment `pypi`.
3. Publique o GitHub Release de novo só se o workflow ainda não tiver enviado ao PyPI. Uma tag já publicada não dispara o workflow outra vez. Se o TestPyPI consumiu a release, faça o upload de produção a partir de um workflow dispatch que você adicionar na hora, ou publique a release só depois de o job apontar para o PyPI. Não publique duas vezes o mesmo arquivo com destinos trocados sem olhar o log.
4. Numa máquina limpa:

```bash
uvx capybucks-mcp==0.1.0 --version
```

Depois, um `initialize` e um `tools/list` por stdio. A lista tem de bater com `tests/contract/snapshots/tools.json`.

## 4. O que não fazer aqui

- Não rode `uv publish` nem `twine upload` nesta entrega.
- Não crie a tag `v0.1.0` até a release ser desejada.
- Não submeta o formulário do marketplace. O checklist da seção 11 do plano pertence ao repo `capybucks-plugin`, e o `mcp.json` desse plugin só pode fixar `==0.1.0` depois que o nome existir no PyPI.
- Não redistribua fixtures de mercado fora dos testes. A nota do `LICENSE` continua valendo.
