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

# Separamos el dominio y las rutas usando comillas independientes
# de esta forma el formateador automático no puede alterar ni recortar las direcciones
ENV MS_DOMINIO="https://packages.microsoft.com"
ENV MS_LLAVE="/keys/microsoft.asc"
ENV MS_REPO_ALPINE="/alpine/v3.19/prod/"

# 2. Descargar e importar la llave pública criptográfica oficial de Microsoft
RUN curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -fsSL "${MS_DOMINIO}${MS_LLAVE}" | gpg --import -

# 3. Crear el archivo del repositorio uniendo las variables de forma exacta y literal
RUN mkdir -p /etc/apk/repositories.d && \
    printf "%s\n" "${MS_DOMINIO}${MS_REPO_ALPINE}" > /etc/apk/repositories.d/mssql-release.repo

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
