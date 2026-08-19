FROM python:3.11-slim-bookworm

ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --upgrade \
    paho-mqtt==2.1.0 \
    pyodbc==5.1.0 \
    asyncodbc==0.2.0

COPY run.py /app/run.py
RUN chmod a+x /app/run.py

ENTRYPOINT ["python3", "/app/run.py"]
