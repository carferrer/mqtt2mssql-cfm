import sys
import json
import logging
import asyncio
import paho.mqtt.client as mqtt
import asyncodbc   # ← Migración completa desde aioodbc

CONFIG_PATH = "/data/options.json"

# ---------------- CONFIG ----------------
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

# ---------------- GLOBALS ----------------
queue = asyncio.Queue()
pool_mssql = None

# ---------------- POOL ----------------
async def inicializar_pool_mssql():
    global pool_mssql
    while True:
        try:
            logging.info("Creando pool MSSQL (10 conexiones)...")

            if pool_mssql:
                pool_mssql.close()
                await pool_mssql.wait_closed()

            pool_mssql = await asyncodbc.create_pool(
                dsn=CONNECTION_STRING,
                minsize=5,
                maxsize=10,
                autocommit=True
            )

            logging.info("Pool MSSQL listo.")
            return
        except Exception as e:
            logging.error(f"Error creando pool: {e}. Reintentando en 5s...")
            await asyncio.sleep(5)

# ---------------- WORKERS ----------------
async def worker_sql():
    global pool_mssql

    while True:
        query_text = await queue.get()
        try:
            async with pool_mssql.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_text)
                    logging.info("Consulta ejecutada correctamente.")
        except Exception as e:
            logging.error(f"Error ejecutando SQL: {e}")
            logging.debug(f"Query:\n{query_text}")
        finally:
            queue.task_done()

# ---------------- MQTT ----------------
def on_message(client, userdata, msg, properties=None):
    try:
        query = msg.payload.decode("utf-8").strip()
        if not query:
            return

        if not query.endswith(";"):
            query += ";"

        asyncio.run_coroutine_threadsafe(queue.put(query), asyncio.get_event_loop())
        logging.debug("Consulta añadida a la cola FIFO.")
    except Exception as e:
        logging.error(f"Error procesando mensaje MQTT: {e}")

# ---------------- MAIN ----------------
async def main():
    await inicializar_pool_mssql()

    for _ in range(10):
        asyncio.create_task(worker_sql())

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_ID, clean_session=True)
    client.on_message = on_message

    if MQTT_USER and MQTT_PWD:
        client.username_pw_set(MQTT_USER, MQTT_PWD)

    logging.info("Conectando a MQTT...")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC, qos=1)
    client.loop_start()

    logging.info(f"Escuchando en MQTT → {MQTT_TOPIC}")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
