# AI Writing Studio

Long-form AI writing application scaffold.

## Stack

- Frontend: Vite + Vue 3 + TypeScript
- Backend: Python + FastAPI
- Architecture: frontend/backend separated, local-first friendly

## Development

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Open the frontend at `http://127.0.0.1:5173`.
