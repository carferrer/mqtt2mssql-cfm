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

# Cola asíncrona nativa y bucle de eventos global
query_queue = asyncio.Queue()
loop = asyncio.get_event_loop()

async def trabajador_mssql_secuencial():
    """Consume la cola asíncrona una a una garantizando el orden FIFO estricto de llegada."""
    while True:
        try:
            logging.info(f"Abriendo conexión persistente asíncrona con MSSQL ({MSSQL_SERVER})...")
            
            # SOLUCIÓN: Pasamos autocommit=True directamente en los parámetros de la conexión asíncrona
            async with aioodbc.connect(dsn=CONNECTION_STRING, loop=loop, autocommit=True) as conn:
                async with conn.cursor() as cursor:
                    logging.info("Tubería persistente asíncrona abierta. Procesando cola en orden cronológico...")
                    
                    while True:
                        # Espera de forma no bloqueante a que entre una query en la cola
                        query_text = await query_queue.get()
                        
                        try:
                            # Se ejecuta de forma asíncrona y ultraveloz
                            await cursor.execute(query_text)
                            logging.info("Consulta individual ejecutada con éxito en orden secuencial.")
                        except Exception as db_error:
                            logging.error(f"Fallo de ejecución en SQL Server (Fila saltada): {db_error}")
                            logging.debug(f"Query afectada:\n{query_text}")
                        finally:
                            # Informa a la cola que el elemento ha sido procesado
                            query_queue.task_done()
                            
        except Exception as e:
            logging.error(f"Error en la conexión persistente asíncrona. Reconectando en 5s... Detalle: {e}")
            await asyncio.sleep(5)

def on_message(client, userdata, msg, properties=None):
    """Recibe el mensaje MQTT de forma instantánea y lo mete al final de la cola asíncrona."""
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if query_recibida:
            if not query_recibida.endswith(';'):
                query_recibida += ';'
            
            # Operación en memoria RAM instantánea: mete la query respetando la fila india
            loop.call_soon_threadsafe(query_queue.put_nowait, query_recibida)
            logging.debug("Consulta guardada en la cola secuencial asíncrona.")
    except Exception as e:
        logging.error(f"Error al procesar el mensaje MQTT: {e}")

async def main():
    # 1. Arrancar el hilo de fondo secuencial asíncrono
    asyncio.create_task(trabajador_mssql_secuencial())

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
    logging.info(f"Escuchando ráfagas asíncronas SECUENCIALES en: {TOPICO_SQL}")

    client.loop_start()

    # Mantener el loop vivo de forma eficiente
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop.run_until_complete(main())
