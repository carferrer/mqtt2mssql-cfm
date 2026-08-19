# Usamos Debian Slim por estabilidad en red con sockets TCP
FROM python:3.11-slim-bookworm

ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

# Forzar a Python a volcar todos los logs a Home Assistant en tiempo real
ENV PYTHONUNBUFFERED=1

# 1. Instalar únicamente las herramientas de compilación básicas de Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar las librerías de Python necesarias para el motor asíncrono multi-conexión
RUN pip3 install --no-cache-dir \
    paho-mqtt==2.1.0 \
    pyodbc==5.1.0 \
    aioodbc==0.3.3

# 3. Copiar el script ejecutor de tu Add-on al contenedor
COPY run.py /run.py
RUN chmod a+x /run.py

CMD [ "python3", "/run.py" ]
