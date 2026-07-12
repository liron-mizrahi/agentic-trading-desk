FROM python:3.11-slim

LABEL description="AI Trading Desk — Agent Layer (Celery Worker)"

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# TA-Lib C library (installed once for future indicator development)
RUN curl -fsSL --retry 3 --retry-delay 5 \
    "https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib_0.6.4_amd64.deb" \
    -o /tmp/ta-lib.deb \
    && dpkg -i /tmp/ta-lib.deb \
    && rm /tmp/ta-lib.deb

WORKDIR /app
ENV PYTHONPATH="/app:${PYTHONPATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/agent/requirements.txt
RUN pip install --no-cache-dir -r /app/agent/requirements.txt

COPY . /app/agent/

CMD ["celery", "-A", "agent.tasks", "worker", "--loglevel=info", "--concurrency=4"]
