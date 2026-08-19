# Usamos Debian Slim por estabilidad en red con sockets TCP
FROM python:3.11-slim-bookworm

ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

# 1. Instalar únicamente las herramientas de compilación básicas de Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar las librerías de Python (pymssql no necesita drivers externos en el sistema)
RUN pip3 install --no-cache-dir \
    paho-mqtt==2.1.0 \
    pymssql==2.3.0

COPY run.py /run.py
RUN chmod a+x /run.py

CMD [ "python3", "/run.py" ]
