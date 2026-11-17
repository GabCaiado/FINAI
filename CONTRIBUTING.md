# Contribuindo com o FINAI

## Fluxo de trabalho

- `main` está sempre verde e implantável. Trabalhe em branches curtas (`feat/b4-classifier`,
  `fix/dedupe-occurrence`) e abra um Pull Request; o CI precisa passar antes do merge.
- Commits seguem [Conventional Commits](https://www.conventionalcommits.org/) com o id do pacote
  de trabalho quando houver: `feat(B4): add user-memory layer to classifier`.
- Um pacote de trabalho por PR. Ideias fora do escopo viram issue, não código no mesmo PR.

## Definição de pronto

1. Critérios de aceite do pacote atendidos e testados.
2. `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `pytest -q`, `npm run lint`, `npm run test` e
   `npm run build` passando (o CI roda tudo isso, inclusive os testes em Postgres).
3. Mudança de schema acompanhada de migração Alembic.
4. Config nova documentada em `backend/.env.example` e no README.

## Regras que não se negociam

- **O backend é determinístico.** O LLM só classifica descrições limpas e explica números já
  calculados; todo acesso a ele passa por `backend/app/ai/provider.py`.
- **Isolamento por usuário.** Toda query que toca dados do usuário filtra por `user_id` vindo do
  token, nunca do corpo da requisição. Outro usuário recebe 404.
- **Dinheiro em centavos inteiros**, nunca `float`.
- **Privacidade (LGPD).** Não logar descrições, valores, prompts ou credenciais; não guardar o
  arquivo bruto enviado; dados de teste e do workshop são sintéticos.
- **Erros da API** usam o contrato `{code, message, details, request_id}` (`app/errors.py`).
- **Sem valores fixos no código.** URLs, portas, limites, timeouts, credenciais e modelos vêm de
  `app/config.py` (sem valor padrão) e entram em `backend/.env.example`, `backend/.env.test` e no
  README. Texto da interface fica em `frontend/src/i18n/pt-BR.ts`.

## Guardrails de arquitetura

```bash
cd backend
lint-imports                          # contratos de camadas/pureza (pyproject.toml)
pytest -q tests/test_architecture.py  # openai, rotas autenticadas, print, os.environ
```

Para abrir uma exceção: em `[tool.importlinter]` adicione a linha em `ignore_imports` do contrato,
**com um comentário dizendo o porquê**; para rota pública, adicione-a a `PUBLIC_ROUTE_ALLOWLIST` em
`tests/test_architecture.py` com o motivo. Justifique a exceção na descrição do PR.

## Ambiente local

Veja o [README](README.md). Resumo:

```bash
cd backend && cp .env.example .env           # preencha; sem .env o app não sobe
alembic upgrade head                         # cria/atualiza o schema
pytest -q                                    # usa backend/.env.test, nunca o seu .env
```

Postgres local é opcional (veja o README: `docker compose up -d db`).

## Migrações

```bash
cd backend
alembic revision --autogenerate -m "describe the change"   # revise o arquivo gerado
alembic upgrade head
```

O teste `tests/test_migrations.py` falha se os modelos e as migrações divergirem.
