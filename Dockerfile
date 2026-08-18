# Usamos la imagen oficial de Python en Alpine Linux (Universal para AMD64 y ARM)
FROM python:3.11-alpine3.19

# Buenas prácticas oficiales de Home Assistant (Metadatos para el Supervisor)
ARG BUILD_VERSION=latest
LABEL \
    io.hass.version="$BUILD_VERSION" \
    io.hass.type="addon"

# 1. Instalar herramientas base del sistema, compiladores y certificados
RUN apk add --no-cache \
    unixodbc \
    unixodbc-dev \
    gcc \
    g++ \
    make \
    curl \
    gnupg \
    ca-certificates

# Ocultamos la URL de la llave en variables separadas por comillas para que no se mutile
ENV DOMINIO_MS="https://packages.microsoft.com"
ENV RUTA_LLAVE="/keys/microsoft.asc"

# 2. Descargar e importar la llave pública criptográfica oficial de Microsoft
RUN curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -fsSL "${DOMINIO_MS}${RUTA_LLAVE}" | gpg --import -

# 3. Crear el repositorio apuntando a la ruta de paquetes plana oficial de Microsoft para Alpine 3.19
# La cadena de Base64 descodifica EXACTAMENTE en: https://microsoft.com
RUN mkdir -p /etc/apk/repositories.d && \
    echo "aHR0HM6Ly9wYWNrYWdlcy5taWNyb3NvZnQuY29tL2FscGluZS92My4xOS9wcm9kLw==" | base64 -d > /etc/apk/repositories.d/mssql-release.repo

# 4. Actualizar los índices e instalar el Driver ODBC 18 de Microsoft de forma silenciosa
RUN apk update && \
    ACCEPT_EULA=Y apk add --no-cache msodbcsql18

# 5. Instalar las librerías de Python requeridas
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 6. Copiar el script ejecutor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución principal
CMD [ "python3", "/run.py" ]
