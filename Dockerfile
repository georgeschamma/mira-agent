FROM node:22-alpine AS ui
WORKDIR /app/ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim AS app
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv sync --no-dev --no-editable
COPY --from=ui /app/ui/dist ./ui/dist
EXPOSE 8123
CMD ["uvicorn", "mira_agent.main:app", "--host", "0.0.0.0", "--port", "8123"]
