# Usamos la imagen oficial de Python en Alpine Linux (Independiente de HA)
FROM python:3.11-alpine3.19

# Instalar dependencias del sistema y herramientas de compilación
RUN apk add --no-cache \
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
RUN apk update && \
    ACCEPT_EULA=Y apk add --no-cache msodbcsql18

# Instalar los paquetes de Python requeridos (En Alpine puro usamos pip sin restricciones)
RUN pip3 install --no-cache-dir \
    paho-mqtt \
    pyodbc

# Copiar el código fuente del add-on
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de inicio
CMD [ "python3", "/run.py" ]
