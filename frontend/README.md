# Aristeus Frontend

React + Vite + TypeScript + Tailwind, ausgeliefert als PWA. Siehe [../PLAN.md](../PLAN.md).

## Local setup (Windows / PowerShell)

```powershell
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173. Der Dev-Server proxyt `/api/*` automatisch nach
`http://localhost:8000` — Backend separat starten (siehe [../backend/README.md](../backend/README.md)).

## Layout

```
src/
  main.tsx        Entrypoint
  App.tsx         Phase-0 Hello World (zeigt /api/health an)
  index.css       Tailwind base
  pages/          (ab Phase 1: Login, Onboarding, Plan, ...)
  components/     (ab Phase 1)
  api/            Typisierter fetch-Wrapper
  hooks/          useAuth, useProfile, usePlan
public/
  favicon.svg
```
