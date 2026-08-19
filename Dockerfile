# Imagen base ligera y estable
FROM python:3.11-slim-bookworm

ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

# Logs sin buffer para Home Assistant
ENV PYTHONUNBUFFERED=1

# Crear directorio de trabajo
WORKDIR /app

# Instalar solo lo necesario para pyodbc/aioodbc
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
RUN pip3 install --no-cache-dir --upgrade \
    paho-mqtt==2.1.0 \
    pyodbc==5.1.0 \
    aioodbc==0.3.3

# Copiar el script principal
COPY run.py /app/run.py
RUN chmod a+x /app/run.py

# Crear usuario no root (opcional pero recomendado)
RUN useradd -m addonuser
USER addonuser

ENTRYPOINT ["python3", "/app/run.py"]
