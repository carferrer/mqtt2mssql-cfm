# Usamos la imagen oficial de Python en Alpine Linux (Universal para AMD64 y ARM)
FROM python:3.11-alpine3.19

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

# Truco de ensamblado: Protegemos la URL para que no sufra ningún recorte de texto
ENV ENLACE_BASE="https://microsoft.com"
ENV RUTA_LLAVE="/keys/microsoft.asc"
ENV RUTA_REPO="/config/alpine/3.19/prod.list"

# 2. Descargar la llave pública de Microsoft usando un User-Agent limpio e importar a GPG
RUN curl -A "Mozilla/5.0" -fsSL "${ENLACE_BASE}${RUTA_LLAVE}" | gpg --import -

# 3. Añadir el repositorio oficial específico de Microsoft para Alpine 3.19
RUN curl -A "Mozilla/5.0" -fsSL -o /etc/apk/repositories.d/mssql-release.repo "${ENLACE_BASE}${RUTA_REPO}"

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
