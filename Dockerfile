# Dockerfile (Final "Pure" Version)

# =================================================================
# STAGE 1: Build Frontend
# =================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# =================================================================
# STAGE 2: Final Production Image
# =================================================================
FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV IS_DOCKER=1
WORKDIR /app
COPY backend/ ./backend
COPY --from=frontend-builder /app/frontend/dist ./backend/app/frontend_dist
RUN pip install --no-cache-dir -r ./backend/requirements.txt
WORKDIR /app/backend
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]