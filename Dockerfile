FROM python:3.11-slim-bookworm

ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Instalar s6-overlay
ADD https://github.com/just-containers/s6-overlay/releases/download/v3.1.5.0/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/v3.1.5.0/s6-overlay-x86_64.tar.xz /tmp/
RUN tar -C / -Jxvf /tmp/s6-overlay-noarch.tar.xz && \
    tar -C / -Jxvf /tmp/s6-overlay-x86_64.tar.xz && \
    rm /tmp/s6-overlay-noarch.tar.xz /tmp/s6-overlay-x86_64.tar.xz

# Dependencias base
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    unixodbc \
    unixodbc-dev \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Instalar ODBC Driver 18
RUN curl https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor \
        | tee /usr/share/keyrings/microsoft.gpg > /dev/null \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        | tee /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# Librerías Python
RUN pip3 install --no-cache-dir --upgrade \
    paho-mqtt==2.1.0 \
    pyodbc==5.1.0 \
    asyncodbc==0.1.1

COPY run.py /app/run.py
RUN chmod a+x /app/run.py

# Copiar rootfs (scripts s6-overlay)
COPY rootfs/ /

ENTRYPOINT ["/init"]
