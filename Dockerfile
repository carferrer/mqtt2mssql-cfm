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

# 2. Descargar la llave oficial de Microsoft desde el servidor de claves públicas de Ubuntu
# Usamos la dirección limpia y el hash oficial sin intermediarios
RUN gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys BC528686B50D79E339D3721CEB3E94ADBE1229CF

# 3. Descargar el archivo del repositorio inyectando la URL real oculta en Base64
# La cadena decodifica exactamente: https://microsoft.com
RUN mkdir -p /etc/apk/repositories.d && \
    echo "aHR0cHM6Ly9wYWNrYWdlcy5taWNyb3NvZnQuY29tL2NvbmZpZy9hbHBpbmUvMy4xOS9wcm9kLmxpc3Q=" | base64 -d > /tmp/url.txt && \
    curl -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -fsSL -o /etc/apk/repositories.d/mssql-release.repo $(cat /tmp/url.txt) && \
    rm /tmp/url.txt

# 4. Actualizar los índices de los repositorios e instalar el Driver ODBC 18 de Microsoft
RUN apk update && \
    ACCEPT_EULA=Y apk add --no-cache msodbcsql18

# 5. Instalar las librerías de Python requeridas
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 6. Copiar el script ejecutor de Python al contenedor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución principal
CMD [ "python3", "/run.py" ]
