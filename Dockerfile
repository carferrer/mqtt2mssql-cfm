# Usamos Debian Slim: Súper estable, compatible con ARM y AMD64, y sin fallos de red en HA
FROM python:3.11-slim-bookworm

# 1. Instalar herramientas del sistema indispensables
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    build-essential \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Añadir la llave y el repositorio oficial de Microsoft para Debian 12 (Bookworm)
RUN curl -fsSL https://microsoft.com | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://microsoft.com bookworm main" > /etc/apt/sources.list.add.d/mssql-release.list

# 3. Actualizar e instalar el Driver ODBC 18 oficial de Microsoft de forma totalmente automática
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# 4. Instalar las librerías de Python
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 5. Copiar el script ejecutor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución principal
CMD [ "python3", "/run.py" ]
