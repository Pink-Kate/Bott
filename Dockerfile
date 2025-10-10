FROM python:3.11-slim

WORKDIR /app

# Копіюємо файли залежностей
COPY requirements.txt .

# Встановлюємо залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо код бота
COPY Bot.py .
COPY B.env .

# Налаштування Python
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "Bot.py"] 