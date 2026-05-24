FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# System dependencies for Playwright and psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (used for Substack automation)
RUN playwright install chromium --with-deps

RUN groupadd --system app && \
    useradd --system --gid app --home-dir /home/app --create-home app && \
    mkdir -p /ms-playwright && \
    chown -R app:app /app /home/app /ms-playwright

COPY . .
RUN chown -R app:app /app

USER app

EXPOSE 8000
