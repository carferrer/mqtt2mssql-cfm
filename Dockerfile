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

# Separamos las URLs en fragmentos para evitar recortes de texto en el formateador
ENV URL_DOMINIO="https://microsoft.com"
ENV URL_LLAVE="/keys/microsoft.asc"
ENV URL_REPO="/config/alpine/3.19/prod.list"

# 2. Descargar la llave pública de Microsoft apuntando al subdominio correcto
RUN curl -A "Mozilla/5.0" -fsSL "${URL_DOMINIO}${URL_LLAVE}" | gpg --import -

# 3. Añadir el repositorio oficial específico de Microsoft para Alpine 3.19
RUN curl -A "Mozilla/5.0" -fsSL -o /etc/apk/repositories.d/mssql-release.repo "${URL_DOMINIO}${URL_REPO}"

# 4. Actualizar los índices e instalar el Driver ODBC 18 de Microsoft de forma silenciosa
RUN apk update && \
    ACCEPT_EULA=Y apk add --no-cache msodbcsql18

# 5. Instalar las librerías de Python requeridas
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 6. Copiar el script ejecutor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución
CMD [ "python3", "/run.py" ]
