## What and why

<!-- One or two sentences. Link the work package (e.g. B4) when there is one. -->

## Checklist

- [ ] Tests added or updated; `pytest -q` and `npm run test` are green
- [ ] `ruff check`, `ruff format --check`, `mypy` and `npm run lint` are green
- [ ] Schema change? A new Alembic migration is included (`alembic revision --autogenerate`)
- [ ] New config? `backend/.env.example` and the README are updated
- [ ] New or changed endpoint? Every query filters by the authenticated `user_id`
- [ ] Nothing logs descriptions, amounts, prompts or credentials; no real personal data in fixtures
- [ ] New dependency? Justified in the PR description
