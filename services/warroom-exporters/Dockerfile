FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir maxminddb==2.6.2
COPY router.py geoip.py security.py main.py /app/
WORKDIR /app
EXPOSE 9117 9118 9119
ENTRYPOINT ["python", "/app/main.py"]
