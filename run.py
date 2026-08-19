import sys
import json
import logging
import asyncio
import paho.mqtt.client as mqtt
import aioodbc

CONFIG_PATH = "/data/options.json"

try:
    with open(CONFIG_PATH, "r") as f:
        config_data = json.load(f)
except Exception as e:
    print(f"[CRITICAL] No se pudo leer la configuración del Add-on: {e}", file=sys.stderr)
    sys.exit(1)

LOG_LEVEL = config_data.get("log_level", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

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

# Cola asíncrona y bucle de eventos global
query_queue = asyncio.Queue()
loop = asyncio.get_event_loop()

# CONFIGURACIÓN DEL MICRO-BATCH (Optimizado para ráfagas)
MICRO_BATCH_INTERVAL = 0.2  # Vacía la cola hacia MSSQL cada 200 milisegundos
MAX_BATCH_SIZE = 50        # Límite de seguridad de consultas por bloque

async def despachador_mssql_micro_batch():
    """Agrupa las consultas de la cola en micro-lotes secuenciales y los inyecta en un solo viaje de red."""
    while True:
        try:
            logging.info(f"Abriendo conexión persistente asíncrona con MSSQL ({MSSQL_SERVER})...")
            async with aioodbc.connect(dsn=CONNECTION_STRING, loop=loop, autocommit=True) as conn:
                async with conn.cursor() as cursor:
                    logging.info("Tubería persistente establecida. Motor Micro-Batch listo.")
                    
                    while True:
                        # Esperamos el intervalo de tiempo fijado para acumular ráfagas en la cola
                        await asyncio.sleep(MICRO_BATCH_INTERVAL)
                        
                        lote_queries = []
                        # Extraemos de la cola todos los mensajes acumulados en este instante
                        while not query_queue.empty() and len(lote_queries) < MAX_BATCH_SIZE:
                            query = query_queue.get_nowait()
                            lote_queries.append(query)
                            query_queue.task_done()
                        
                        if lote_queries:
                            # Unimos las consultas con saltos de línea e indicamos SET NOCOUNT ON 
                            # para eliminar el tráfico de red de retorno que bloquea a MSSQL
                            script_completo = "SET NOCOUNT ON;\n" + "\n".join(lote_queries)
                            
                            try:
                                # Viaja todo el bloque agrupado en un único milisegundo por la red
                                await cursor.execute(script_completo)
                                logging.info(f"Micro-lote inyectado con éxito: {len(lote_queries)} consultas procesadas.")
                            except Exception as db_error:
                                logging.error(f"Fallo de ejecución en bloque SQL Server: {db_error}")
                                logging.debug(f"Script del bloque afectado:\n{script_completo}")
                                
        except Exception as e:
            logging.error(f"Error en la conexión persistente. Reconectando en 5s... Detalle: {e}")
            await asyncio.sleep(5)

def on_message(client, userdata, msg, properties=None):
    """Recibe los mensajes de MQTT instantáneamente y los mete a la cola en microsegundos."""
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if query_recibida:
            if not query_recibida.endswith(';'):
                query_recibida += ';'
            
            # Coloca la consulta en la cola respetando la fila india
            loop.call_soon_threadsafe(query_queue.put_nowait, query_recibida)
            logging.debug("Consulta encolada en el buffer asíncrono.")
    except Exception as e:
        logging.error(f"Error al procesar el mensaje MQTT: {e}")

async def main():
    # 1. Arrancar el consumidor de micro-lotes de fondo
    asyncio.create_task(despachador_mssql_micro_batch())

    # 2. Configurar cliente MQTT integrado
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
    logging.info(f"Escuchando ráfagas asíncronas en: {TOPICO_SQL}")

    client.loop_start()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop.run_until_complete(main())
