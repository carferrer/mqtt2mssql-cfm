# Usamos Debian Slim como base estable
FROM python:3.11-slim-bookworm

# 1. Instalar herramientas del sistema y dependencias de compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Descargar e instalar el configurador automático de repositorios oficiales de Microsoft
# Este paquete .deb configura las llaves y el catálogo APT de forma nativa sin usar comandos gpg manuales
RUN curl -sSLO https://microsoft.com \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb

# 3. Actualizar la lista de APT (ahora con el repositorio oficial) e instalar MS ODBC 18
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# 4. Instalar las librerías de Python requeridas
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 5. Copiar el archivo ejecutor de Python al contenedor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución principal
CMD [ "python3", "/run.py" ]
