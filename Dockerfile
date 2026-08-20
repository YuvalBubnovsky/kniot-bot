FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY categories.py bot.py .

VOLUME /app/data

ENV DB_PATH=/app/data/shopping.db

CMD ["python3", "bot.py"]
