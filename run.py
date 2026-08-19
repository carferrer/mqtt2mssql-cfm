import sys
import json
import logging
import asyncio
import paho.mqtt.client as mqtt
import aioodbc  # El driver asíncrono para manejar el Pool

# Ruta oficial donde Home Assistant guarda las opciones de la interfaz del Add-on
CONFIG_PATH = "/data/options.json"

try:
    with open(CONFIG_PATH, "r") as f:
        config_data = json.load(f)
except Exception as e:
    print(f"[CRITICAL] No se pudo leer la configuración del Add-on: {e}", file=sys.stderr)
    sys.exit(1)

# Extraer el nivel de log configurado por el usuario (por defecto INFO)
LOG_LEVEL = config_data.get("log_level", "INFO").upper()

# Configurar el formato profesional de los logs para Home Assistant
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# Extraer las credenciales dinámicas de la configuración
MSSQL_SERVER = config_data.get("mssql_server", "mssqlserver")
MSSQL_PORT = config_data.get("mssql_port", 1433)
MSSQL_DB = config_data.get("mssql_database", "mssqlbbdd")
MSSQL_USER = config_data.get("mssql_user", "mssqluser")
MSSQL_PWD = config_data.get("mssql_password", "mssqlpwd")

MQTT_HOST = config_data.get("mqtt_host", "core-mosquitto")
MQTT_PORT = config_data.get("mqtt_port", 1883)
MQTT_USER = config_data.get("mqtt_user", "mqttuser")
MQTT_PWD = config_data.get("mqtt_password", "mqttpwd")
MQTT_ID = config_data.get("mqtt_id", "mqttid")
MQTT_TOPIC = config_data.get("mqtt_topic", "mqtt2mssqltopic")

CONNECTION_STRING = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={MSSQL_SERVER},{MSSQL_PORT};"
    f"DATABASE={MSSQL_DB};"
    f"UID={MSSQL_USER};"
    f"PWD={MSSQL_PWD};"
    f"TrustServerCertificate=yes;"
)

# Variables globales para el bucle y el Pool asíncrono
pool_mssql = None
loop = asyncio.get_event_loop()

# LA CLAVE DEL ORDEN: Un semáforo asíncrono que garantiza que las consultas 
# se lancen al pool estrictamente en su orden de llegada por MQTT
semaphore = asyncio.Semaphore(1)

async def inicializar_pool_mssql():
    """Crea un pool dinámico de hasta 10 conexiones simultáneas abiertas (Igual que Node-RED)."""
    global pool_mssql
    while True:
        try:
            logging.info(f"Abriendo Pool de 10 conexiones persistentes con MSSQL ({MSSQL_SERVER})...")
            pool_mssql = await aioodbc.create_pool(
                dsn=CONNECTION_STRING, 
                minsize=5, 
                maxsize=10, # <-- Abre hasta 10 sesiones en tu MSSQL
                loop=loop,
                autocommit=True # Inyección directa ultrarrápida
            )
            logging.info("Pool dinámico establecido. 10 canales listos para ráfagas.")
            break
        except Exception as e:
            logging.error(f"Error al levantar el Pool de conexiones: {e}. Reintentando en 5s...")
            await asyncio.sleep(5)

async def ejecutar_sql_en_pool(query_text):
    """Inyecta la consulta usando una de las 10 conexiones libres del pool de forma asíncrona."""
    global pool_mssql
    
    # El semáforo asegura que las consultas entren al pool en orden FIFO estricto
    async with semaphore:
        try:
            if pool_mssql is None:
                await inicializar_pool_mssql()
                
            # Toma instantáneamente una de las 10 sesiones abiertas en microsegundos
            async with pool_mssql.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_text)
                    logging.info("Consulta inyectada con éxito a través del Pool multi-sesión.")
        except Exception as db_error:
            logging.error(f"Fallo de ejecución individual en el Pool: {db_error}")
            logging.debug(f"Query afectada:\n{query_text}")

def on_message(client, userdata, msg, properties=None):
    """Recibe los mensajes de MQTT y los despacha al loop asíncrono sin bloquear la red."""
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if query_recibida:
            if not query_recibida.endswith(';'):
                query_recibida += ';'
            
            # Delegamos la tarea al Pool respetando la marca de tiempo de llegada
            asyncio.run_coroutine_threadsafe(ejecutar_sql_en_pool(query_recibida), loop)
            logging.debug("Consulta enviada al administrador del Pool.")
    except Exception as e:
        logging.error(f"Error en recepción MQTT: {e}")

async def main():
    # 1. Levantar las 10 sesiones persistentes de base de datos
    await inicializar_pool_mssql()

    # 2. Conectar el cliente MQTT
    CLIENT_ID = MQTT_ID
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
    client.on_message = on_message

    if MQTT_USER and MQTT_PWD:
        client.username_pw_set(username=MQTT_USER, password=MQTT_PWD)
        logging.info(f"Aplicando credenciales para el usuario MQTT: {MQTT_USER}")

    logging.info("Conectando al bróker MQTT...")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    
    TOPICO_SQL = MQTT_TOPIC
    client.subscribe(TOPICO_SQL, qos=1)
    logging.info(f"Escuchando ráfagas concurrentes en: {TOPICO_SQL}")

    client.loop_start()

    # Mantener el bucle asíncrono principal activo
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop.run_until_complete(main())
