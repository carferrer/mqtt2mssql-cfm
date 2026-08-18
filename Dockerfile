# Usamos la imagen oficial de Python en Alpine Linux (Independiente de HA)
FROM python:3.11-alpine3.19

ARG BUILD_VERSION=latest
LABEL io.hass.version="$BUILD_VERSION" io.hass.type="addon" io.hass.arch="aarch64|amd64"

# Instalar dependencias del sistema y herramientas de compilación
RUN apk add --no-cache \
    unixodbc \
    unixodbc-dev \
    gcc \
    g++ \
    make \
    curl \
    gnupg

# 2. Descargar la llave pública de Microsoft e importar al llavero de GPG
RUN curl -sSL https://microsoft.com | gpg --import -

# 3. Añadir el repositorio oficial específico de Microsoft para Alpine 3.19
RUN curl -sSL -o /etc/apk/repositories.d/mssql-release.repo https://microsoft.com

# 4. Actualizar los índices e instalar el Driver ODBC 18 de Microsoft
# ACCEPT_EULA=Y acepta la licencia obligatoria en modo silencioso
RUN apk update && \
    ACCEPT_EULA=Y apk add --no-cache msodbcsql18

# 5. Instalar las librerías de Python requeridas
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 6. Copiar el script que lee la configuración de la interfaz e inicia el bucle MQTT
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución
CMD [ "python3", "/run.py" ]
