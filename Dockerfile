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

# Truco de ensamblado: dividimos la dirección exacta para que no sufra ningún recorte de texto
ENV ENLACE_BASE="https://packages.microsoft.com"
ENV RUTA_PAQUETE="/config/debian/12/packages-microsoft-prod.deb"

# 2. Descargar e instalar el configurador automático uniendo las dos partes de forma exacta
RUN curl -A "Mozilla/5.0" -fsSLO "${ENLACE_BASE}${RUTA_PAQUETE}" \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb

# 3. Actualizar la lista de APT e instalar MS ODBC 18
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# 4. Instalar las librerías de Python requeridas
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 5. Copiar tu script ejecutor de Python al contenedor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución principal
CMD [ "python3", "/run.py" ]
