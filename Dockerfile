FROM python:3.11-slim-bookworm

ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencias base
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    unixodbc \
    unixodbc-dev \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Instalar ODBC Driver 18 para SQL Server
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/12/prod.list \
        -o /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18

# Python libs
RUN pip3 install --no-cache-dir --upgrade \
    paho-mqtt==2.1.0 \
    pyodbc==5.1.0 \
    asyncodbc==0.1.1

COPY run.py /app/run.py
RUN chmod a+x /app/run.py

ENTRYPOINT ["python3", "/app/run.py"]
