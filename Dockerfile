# Runs the API and serves the frontend from one container.
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

# SQLite file lives here unless DATABASE_URL points at Postgres.
ENV DATABASE_URL=sqlite:////app/data/splitwise.db
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
