FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Copy requirements and install python packages
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN playwright install chromium

# Copy application source
COPY server/app.py .

# Expose default port
EXPOSE 8888

# Environment variables with sensible defaults
ENV PORT=8888 \
    STORAGE_DIR=/app/snapshots \
    RETENTION_DAYS=90 \
    PYTHONUNBUFFERED=1

CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8888"]
