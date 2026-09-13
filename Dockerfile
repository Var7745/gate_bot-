FROM python:3.11-slim

WORKDIR /app

# The bot relies exclusively on Python standard library modules (urllib, json, ssl, time, threading)
# No heavy third party wheel compilation needed!
COPY . /app

ENV PYTHONUNBUFFERED=1

CMD ["python", "scripts/bot_service.py"]
