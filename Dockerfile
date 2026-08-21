FROM python:3.11-slim-bookworm

ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Madrid

WORKDIR /app

# Dependencias base mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    curl \
    gnupg \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Instalar ODBC Driver 18 para SQL Server
RUN curl https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor \
        | tee /usr/share/keyrings/microsoft.gpg > /dev/null \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        | tee /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# Librerías Python
RUN pip3 install --no-cache-dir --upgrade \
    paho-mqtt==2.1.0 \
    pyodbc==5.1.0

COPY run.py /app/run.py
RUN chmod a+x /app/run.py

ENTRYPOINT ["python3", "/app/run.py"]
