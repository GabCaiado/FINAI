# FINAI — Frontend

SPA em React + TypeScript + Vite, estilizada com Tailwind CSS.

```bash
npm install
npm run dev         # servidor de desenvolvimento (proxy /api -> http://localhost:8000)
npm run lint        # oxlint
npm run test        # vitest
npm run build       # tsc + vite build
```

## Convenções

- Dinheiro trafega como **centavos inteiros**; a formatação em BRL fica só em `src/lib/money.ts`.
- Chamadas à API usam caminhos relativos `/api/*` (mesma origem, em dev via proxy do Vite e em
  produção via rewrite da Vercel).
- Textos exibidos ao usuário em português (Brasil); código e comentários em inglês.
