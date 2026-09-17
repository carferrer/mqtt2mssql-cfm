ARG BUILD_FROM=ghcr.io/hassio-addons/debian-base:9.4.0
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Environment
ENV \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Python, Microsoft ODBC Driver 18 and Python dependencies
# hadolint ignore=DL3008
RUN \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        unixodbc \
    && apt-get install -y --no-install-recommends \
        g++ \
        python3-dev \
        python3-pip \
        python3-venv \
        unixodbc-dev \
    && curl -fsSL -o /tmp/packages-microsoft-prod.deb \
        https://packages.microsoft.com/config/debian/13/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade \
        paho-mqtt==2.1.0 \
        pyodbc==5.2.0 \
        asyncodbc==0.1.1 \
    && apt-get purge -y --auto-remove \
        g++ \
        python3-dev \
        python3-pip \
        python3-venv \
        unixodbc-dev \
    && apt-get clean \
    && rm -rf \
        /tmp/* \
        /var/lib/apt/lists/*

# Copy application and S6 service definition
WORKDIR /app
COPY run.py /app/run.py
COPY rootfs /

RUN chmod a+x \
    /app/run.py \
    /etc/s6-overlay/s6-rc.d/mqtt2mssql/run

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    maintainer="Carlos <carferrermar@gmail.com>" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Home Assistant Community Apps" \
    org.opencontainers.image.authors="Carlos <carferrermar@gmail.com>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/carferrer/mqtt2mssql-cfm" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"
