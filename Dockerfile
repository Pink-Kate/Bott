FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Bot.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "Bot.py"]
