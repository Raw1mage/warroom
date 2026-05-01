FROM python:3.12-slim

WORKDIR /app
COPY app.py /app/app.py
RUN pip install --no-cache-dir maxminddb==2.6.2

ENV PYTHONUNBUFFERED=1
EXPOSE 8010

CMD ["python", "/app/app.py"]
