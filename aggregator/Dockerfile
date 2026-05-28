FROM python:3.12-slim

WORKDIR /app

# システム依存
RUN apt-get update && apt-get install -y --no-install-recommends \
        cron \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Tokyo

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# cron 設定
COPY crontab /etc/cron.d/whisky-rss
RUN chmod 0644 /etc/cron.d/whisky-rss && crontab /etc/cron.d/whisky-rss

# 起動時に1回走らせてから cron foreground
CMD ["sh", "-c", "python /app/main.py || true; cron -f"]
