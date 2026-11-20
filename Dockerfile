FROM node:24-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS python-wheels
COPY packages/shared_auth /build/shared_auth
RUN pip wheel --no-deps --wheel-dir /wheels /build/shared_auth
COPY requirements.txt /build/requirements.txt
RUN pip wheel --find-links /wheels --wheel-dir /wheels -r /build/requirements.txt

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=python-wheels /wheels /wheels
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-index --find-links /wheels -r /tmp/requirements.txt && rm -rf /wheels
WORKDIR /app

FROM runtime AS auth
COPY services/auth /app/services/auth
WORKDIR /app/services/auth
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-"]

FROM runtime AS main
COPY services/main /app/services/main
COPY --from=frontend-build /frontend/dist /app/frontend/dist
WORKDIR /app/services/main
RUN SECRET_KEY=asset-build-only DEBUG=0 python manage.py collectstatic --noinput
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-"]
