FROM python:3.12-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ../requirements.txt /app/requirements.txt
COPY requirements.txt /app/web_requirements.txt

RUN pip install --no-cache-dir -r requirements.txt -r web_requirements.txt

COPY ../bot_client.py /app/bot_client.py
COPY ../config/ /app/config/
COPY . /app/web/

WORKDIR /app/web

EXPOSE 8000

CMD ["python", "run_web.py", "8000"]
