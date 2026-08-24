# Build stage for frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# Production stage
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir uvicorn

# Copy application code
COPY . .

# Copy built frontend
COPY --from=frontend-build /app/web/dist ./web/dist

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# Run
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
