FROM python:3.12-slim

RUN apt-get update && apt-get install -y ffmpeg curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod +x /usr/local/bin/yt-dlp && \
    yt-dlp --version

WORKDIR /app

COPY requirements.txt .
COPY web/requirements.txt web_requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r web_requirements.txt

RUN mkdir -p /root/.config/yt-dlp
COPY config/yt-dlp.conf /root/.config/yt-dlp/config

COPY bot_client.py .
COPY config/ config/
COPY web/ web/

WORKDIR /app/web

EXPOSE 8000

CMD ["python", "run_web.py", "8000"]
