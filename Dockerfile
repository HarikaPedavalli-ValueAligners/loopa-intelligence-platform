FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8787

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8787\")}/health', timeout=5)"

CMD ["python", "api/server.py", "--host", "0.0.0.0", "--port", "8787"]
