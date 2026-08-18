# Usamos Debian Slim (Estable y universal)
FROM python:3.11-slim-bookworm

# 1. Instalar herramientas base esenciales
RUN apt-get update
RUN apt-get install -y --no-install-recommends curl gnupg ca-certificates build-essential unixodbc unixodbc-dev
RUN rm -rf /var/lib/apt/lists/*

# 2. Descargar la llave de Microsoft de forma aislada a un archivo temporal
RUN curl -fsSL "https://microsoft.com" -o "/tmp/microsoft.asc"

# 3. Convertir la llave al formato oficial gpg seguro
RUN gpg --dearmor -o "/usr/share/keyrings/microsoft-prod.gpg" "/tmp/microsoft.asc"

# 4. Crear la ruta de fuentes e inyectar el repositorio oficial de Microsoft para Debian 12
RUN mkdir -p /etc/apt/sources.list.d
RUN echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://microsoft.com bookworm main" > /etc/apt/sources.list.d/mssql-release.list

# 5. Actualizar los nuevos repositorios e instalar el Driver ODBC 18 oficial de Microsoft
RUN apt-get update
RUN ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18
RUN rm -rf /var/lib/apt/lists/*

# 6. Instalar las librerías de Python
RUN pip3 install --no-cache-dir paho-mqtt pyodbc

# 7. Copiar y preparar el script ejecutor
COPY run.py /run.py
RUN chmod a+x /run.py

# Comando de ejecución
CMD [ "python3", "/run.py" ]
