FROM node:24-bookworm-slim AS web
WORKDIR /source/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN npm install --global pnpm@11.25.0 && pnpm install --frozen-lockfile --ignore-scripts
COPY frontend/ ./
ENV CI=1 EXPO_NO_TELEMETRY=1 EXPO_PUBLIC_GOOGLE_LOGIN_ENABLED=false
RUN pnpm exec expo export --platform web --output-dir /web

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Kolkata
WORKDIR /app/backend
COPY backend/requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY backend/ ./
COPY --from=web /web /app/web
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn hosted_app:create_app --factory --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-access-log"]
