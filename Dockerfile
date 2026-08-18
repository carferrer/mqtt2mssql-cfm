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

# 2. IMPORTACIÓN LOCAL DE LA LLAVE
# Copiamos el archivo físico creado en tu PC e importamos a GPG
COPY microsoft.asc /tmp/microsoft.asc
RUN gpg --import /tmp/microsoft.asc && rm /tmp/microsoft.asc

# 3. CONFIGURACIÓN LOCAL DEL REPOSITORIO
# Copiamos tu archivo local directamente a la ruta maestra de Alpine
COPY prod.list /etc/apk/repositories.d/mssql-release.repo

# 4. Actualizar los índices e instalar el Driver ODBC 18 de Microsoft de forma silenciosa
RUN apk update && \
    ACCEPT_EULA=Y apk add --no-cache --allow-untrusted msodbcsql18

# 5. Instalar las librerías de Python requeridas
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 6. Copiar el script ejecutor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución principal
CMD [ "python3", "/run.py" ]
