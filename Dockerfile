FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY bot ./bot
COPY backtest.py .
CMD ["python", "-m", "bot.main"]
