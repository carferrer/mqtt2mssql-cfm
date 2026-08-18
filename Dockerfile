# Usamos la imagen oficial de Python basada en Ubuntu (Estable, universal y con soporte premium de MS)
FROM python:3.11-slim-bookworm

# Buenas prácticas oficiales de Home Assistant (Metadatos para el Supervisor)
ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64"

ENV PYTHONUNBUFFERED=1

# 1. Instalar herramientas indispensables del sistema Ubuntu/Debian y limpiar cachés
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    build-essential \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Descargar e importar la llave pública criptográfica oficial de Microsoft para APT
# La cadena Base64 descodifica EXACTAMENTE en: https://packages.microsoft.com/keys/microsoft.asc
RUN URL_LLAVE=$(echo "aHR0cHM6Ly9wYWNrYWdlcy5taWNyb3NvZnQuY29tL2tleXMvbWljcm9zb2Z0LmFzYw==" | base64 -d) \
    && curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -fsSL "$URL_LLAVE" | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

# 3. Registrar el repositorio oficial de Microsoft específico para Debian/Ubuntu
# La cadena Base64 descodifica EXACTAMENTE en: https://microsoft.com
RUN URL_REPO=$(echo "aHR0cHM6Ly9wYWNrYWdlcy5taWNyb3NvZnQuY29tL2RlYmlhbi8xMi9wcm9k" | base64 -d) \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] $URL_REPO bookworm main" > /etc/apt/sources.list.d/mssql-release.list

# 4. Actualizar los índices de APT e instalar el Driver ODBC 18 oficial de Microsoft
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# 5. Instalar las librerías de Python requeridas (Mqtt y el compilador de pyodbc)
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 6. Copiar el script ejecutor de tu Add-on al contenedor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución principal
CMD [ "python3", "/run.py" ]
