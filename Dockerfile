# Використовуємо офіційний Python образ з підтримкою SQLite
FROM python:3.11-slim

# Встановлюємо системні залежності
RUN apt-get update && apt-get install -y \
    sqlite3 \
    libsqlite3-dev \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Встановлюємо робочу директорію
WORKDIR /app

# Копіюємо файл залежностей
COPY requirements.txt .

# Встановлюємо Python залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо код бота
COPY Bot.py .

# Налаштування Python
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "Bot.py"]



