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

# Truco definitivo: Separamos el dominio de las rutas con comillas independientes
# para evitar por completo que el formateador automatizado mutile las direcciones
ENV MS_DOM="https://packages.microsoft.com"
ENV MS_KEY="/keys/microsoft.asc"
ENV MS_REP="/config/alpine/3.19/prod.list"

# 2. Descargar la llave oficial directamente desde el servidor de Microsoft con User-Agent completo
RUN curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
    -fsSL "${MS_DOM}${MS_KEY}" | gpg --import -

# 3. Descargar el índice del repositorio oficial de Microsoft para Alpine 3.19
RUN curl -A "Mozilla/5.0" -fsSL -o /etc/apk/repositories.d/mssql-release.repo "${MS_DOM}${MS_REP}"

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
