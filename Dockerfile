ARG BUILD_FROM=homeassistant/amd64-base-alpine:3.19
FROM $BUILD_FROM

# Instalar dependencias del sistema y herramientas de compilación
RUN apk add --no-cache \
    python3 \
    py3-pip \
    unixodbc \
    unixodbc-dev \
    gcc \
    g++ \
    make \
    curl \
    gnupg

# Añadir las llaves y el repositorio oficial de Microsoft para Alpine
RUN curl -O https://microsoft.com && \
    gpg --import microsoft.asc && \
    curl -O https://microsoft.com && \
    mv prod.list /etc/apk/repositories.d/mssql-release.repo

# Instalar el driver oficial de Microsoft ODBC 18 para SQL Server
# ACCEPT_EULA=Y es obligatorio para aceptar los términos de Microsoft
RUN apk update && \
    ACCEPT_EULA=Y apk add --no-cache msodbcsql18

# Instalar los paquetes de Python requeridos
RUN pip3 install --no-cache-dir --break-system-packages \
    paho-mqtt \
    pyodbc

# Copiar el código fuente del add-on
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de inicio
CMD [ "python3", "/run.py" ]
