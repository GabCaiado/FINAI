# FINAI

Aplicativo web gratuito e mobile-first que ajuda estudantes a organizar suas finanças pessoais.
Projeto de extensão da Uninorte (PEX-MDL-54).

O usuário registra receitas e despesas ou importa extratos (CSV/PDF); uma IA classifica as
transações, e um painel, metas e um assistente de chat explicam os números.

> O FINAI não é um banco, não movimenta dinheiro e nunca pede senhas ou tokens.
> Os dados usados no workshop são exclusivamente sintéticos (LGPD).

## Princípio de arquitetura

- **O backend é determinístico.** Somas, saldos, percentuais, metas e recorrência são calculados
  em Python/SQL a partir de transações confirmadas.
- **O LLM só faz duas coisas:** classificar descrições limpas em uma lista fixa de categorias e
  explicar números que o backend já calculou. Nunca calcula nem lê o banco.
- Todo acesso ao LLM passa por `backend/app/ai/provider.py`.

## Stack

| Camada   | Tecnologias                                                                   |
| -------- | ----------------------------------------------------------------------------- |
| Backend  | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, pdfplumber, argon2           |
| Frontend | React, Vite, TypeScript, Tailwind CSS, React Router, Recharts, Vitest         |
| Dados    | SQLite (local), PostgreSQL (produção)                                         |
| Deploy   | Vercel (frontend), Render ou Railway (backend), Neon ou Supabase (Postgres)   |

## Estrutura

```text
.
├── backend/            # API FastAPI
│   ├── app/            # código da aplicação (routers, services, ai, models)
│   ├── migrations/     # migrações Alembic (dono do schema)
│   └── tests/          # testes (pytest)
├── frontend/           # SPA React + Vite
│   └── src/
├── data/synthetic/     # gerador de dados sintéticos e golden set
└── .github/workflows/  # CI
```

## Como rodar

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env             # TODAS as variáveis vêm daqui; ajuste os valores
alembic upgrade head             # cria o schema (a aplicação não cria tabelas sozinha)
uvicorn app.main:app --reload    # http://localhost:8000  (docs em /docs)
```

SQLite funciona para rodar rápido. Para usar o mesmo banco de produção (Postgres) localmente:

```bash
cp .env.example .env             # na raiz: usuário, senha, banco e porta do Postgres
docker compose up -d db          # o compose para se alguma variável faltar
# em backend/.env: DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@localhost:PORTA/BANCO
```

```bash
pytest -q                        # testes (LLM_PROVIDER=mock, sem rede)
pytest -m eval                   # avaliação do golden set (chama a API paga)
ruff check . && ruff format .    # lint e formatação
mypy                             # tipagem estática de app/
alembic revision --autogenerate -m "descreva a mudança"   # nova migração
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env             # API_PROXY_TARGET: para onde o dev server encaminha /api
npm run dev                      # http://localhost:5173
npm run test
npm run build
```

## Configuração

**Nada de configuração fica fixo no código.** Cada valor vem de variável de ambiente ou de um arquivo
`.env`, e o app não tem valores padrão: se faltar uma variável ele não sobe e diz qual é.

| Arquivo | Para quê | Versionado |
| --- | --- | --- |
| `backend/.env.example` | Modelo de todas as variáveis do backend | sim |
| `backend/.env` | Seus valores locais (segredos incluídos) | **não** |
| `backend/.env.test` | Perfil dos testes (sem segredos) | sim |
| `frontend/.env.example` / `.env` | Destino do proxy `/api` no dev server | modelo sim, `.env` não |
| `.env.example` / `.env` (raiz) | Credenciais do Postgres local do `docker-compose` | modelo sim, `.env` não |

Variáveis reais do ambiente sobrescrevem o arquivo (é assim que a hospedagem e o CI configuram o app).
Com `LLM_PROVIDER=mock` o app roda sem rede, usando só regras.
Com `ENVIRONMENT=production` o app se recusa a subir com configuração insegura (segredo curto,
cookie sem `Secure`, SQLite, CORS em `http://`, chave do LLM ausente).

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md): fluxo de branches e PRs, definição de pronto e as regras
que não se negociam (backend determinístico, isolamento por usuário, LGPD).
