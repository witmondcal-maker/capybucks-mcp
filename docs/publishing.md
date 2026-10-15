# Publicação

Nada disto foi executado. Não publique a partir de um agente sem um pedido explícito de release. Não submeta o marketplace a partir deste repositório: o plugin mora em `capybucks-plugin`, que este plano deixa para outro repo.

Versão deste código: `0.1.0` em `pyproject.toml`. Nome no PyPI: `capybucks-mcp`. Em 2026-10-14 o plano registrou que esse nome respondia HTTP 404 no PyPI. Conferido de novo em 2026-10-15: `https://pypi.org/pypi/capybucks-mcp/json` e `https://test.pypi.org/pypi/capybucks-mcp/json` ainda respondem 404. Confira de novo imediatamente antes de publicar.

O workflow `.github/workflows/publish.yml` escolhe o índice sem editar o arquivo.

- **TestPyPI:** Actions → publish → Run workflow, input `target=testpypi`. O job `publish-testpypi` usa o environment `testpypi` e `repository-url: https://test.pypi.org/legacy/`.
- **PyPI:** uma GitHub Release publicada (`release: types: [published]`) dispara o job `publish-pypi` no environment `pypi`. O mesmo job também roda com Run workflow e `target=pypi`.

Os dois jobs de envio dependem do job `build`, que faz `uv sync --locked --all-groups`, `pytest` e `uv build`. Numa release, o `build` ainda confere se a tag sem o prefixo `v` é igual a `project.version`. O dispatch manual não exige tag.

## 1. Pending publisher (manual, Ricardo)

No TestPyPI e no PyPI, em separado:

1. Conta com permissão de criar o projeto `capybucks-mcp` (ou o projeto vazio, se a conta exigir criá-lo antes).
2. Publishing → add a new pending publisher.
3. Owner: `witmondcal-maker`. Repository: `capybucks-mcp`. Workflow: `publish.yml`.
4. Environment do TestPyPI: `testpypi`. Environment do PyPI: `pypi`.

No GitHub, os environments `testpypi` e `pypi` precisam existir e permitir o OIDC desse repositório. O token de cada um aponta para um índice. Sem o pending publisher correspondente, o job falha na hora de enviar.

## 2. TestPyPI primeiro

1. Confirme que o commit que deve sair como `0.1.0` está no branch que o workflow vai ler (o dispatch usa o branch escolhido na hora de rodar).
2. Crie os environments e os pending publishers da seção 1, se ainda não existirem.
3. Rode o workflow `publish` com `target=testpypi`. Não edite `publish.yml`.
4. Verifique:

```bash
uvx --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    capybucks-mcp --version
```

O `--extra-index-url` é necessário porque `capybucks` e `mcp` estão no PyPI, não no TestPyPI.

## 3. PyPI

Quando o TestPyPI responder `--version` com `0.1.0`:

1. Confirme o pending publisher no PyPI de produção, environment `pypi`.
2. Crie a tag `v0.1.0` apontando para o commit. A tag tem de coincidir com `project.version`.
3. Publique um GitHub Release a partir dessa tag. Isso dispara `publish-pypi`. Se a release já foi publicada e o envio ao PyPI não aconteceu, rode o workflow com `target=pypi` em vez de republicar a mesma release. Não edite `publish.yml` para trocar o índice.
4. Numa máquina limpa:

```bash
uvx capybucks-mcp==0.1.0 --version
```

Depois, um `initialize` e um `tools/list` por stdio. A lista tem de bater com `tests/contract/snapshots/tools.json`.

## 4. O que não fazer aqui

- Não rode `uv publish` nem `twine upload` nesta entrega.
- Não crie a tag `v0.1.0` até a release ser desejada.
- Não edite `publish.yml` para apontar o TestPyPI ou o PyPI. O input `target` e o evento de release já escolhem o job.
- Não submeta o formulário do marketplace. O checklist da seção 11 do plano pertence ao repo `capybucks-plugin`, e o `mcp.json` desse plugin só pode fixar `==0.1.0` depois que o nome existir no PyPI.
- Não redistribua fixtures de mercado fora dos testes. O sdist e o wheel excluem `tests/fixtures`. A nota do `LICENSE` continua valendo.
