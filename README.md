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
| Backend  | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, pandas, pdfplumber, argon2   |
| Frontend | React, Vite, TypeScript, Tailwind CSS, React Router, Recharts, Vitest         |
| Dados    | SQLite (local), PostgreSQL (produção)                                         |
| Deploy   | Vercel (frontend), Render ou Railway (backend), Neon ou Supabase (Postgres)   |

## Estrutura

```text
.
├── backend/            # API FastAPI
│   ├── app/            # código da aplicação (routers, services, ai, models)
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
cp .env.example .env             # ajuste as variáveis
uvicorn app.main:app --reload    # http://localhost:8000
```

```bash
pytest -q                        # testes (LLM_PROVIDER=mock, sem rede)
pytest -m eval                   # avaliação do golden set (chama a API paga)
ruff check . && ruff format .    # lint e formatação
```

### Frontend

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173 (proxy /api -> :8000)
npm run test
npm run build
```

## Configuração

Variáveis de ambiente do backend estão documentadas em [`backend/.env.example`](backend/.env.example).
Nunca faça commit de `.env`. Com `LLM_PROVIDER=mock` o app roda sem rede, usando só regras.
