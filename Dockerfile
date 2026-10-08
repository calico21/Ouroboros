# syntax=docker/dockerfile:1
FROM node:20-slim AS frontend-build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app/applet

# Install system dependencies & Node.js for dual execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    supervisor \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy package and dependencies
COPY package*.json ./
RUN npm install --omit=dev

# Copy source and built assets
COPY . .
COPY --from=frontend-build /app/dist /app/applet/dist

# Create necessary directories
RUN mkdir -p /app/applet/reports/logs /app/applet/reports/telemetry /app/applet/reports/audit

EXPOSE 3000

ENV PORT=3000
ENV PYTHONPATH=/app/applet

CMD ["supervisord", "-c", "/app/applet/supervisord.conf"]
