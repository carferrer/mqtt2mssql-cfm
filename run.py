#!/usr/bin/env python3
import asyncio
import logging
import paho.mqtt.client as mqtt
import asyncodbc
import json
import os

# ---------------------------------------------------------
# CARGAR CONFIGURACIÓN DEL ADD-ON
# ---------------------------------------------------------
CONFIG_PATH = "/data/options.json"

try:
    with open(CONFIG_PATH, "r") as f:
        config_data = json.load(f)
except Exception as e:
    print(f"ERROR cargando configuración {CONFIG_PATH}: {e}")
    config_data = {}

# ---------------------------------------------------------
# CONFIGURACIÓN MSSQL
# ---------------------------------------------------------
MSSQL_SERVER = config_data.get("mssql_server", "mssqlserver")
MSSQL_PORT = config_data.get("mssql_port", 1433)
MSSQL_DB = config_data.get("mssql_database", "mssqlbbdd")
MSSQL_USER = config_data.get("mssql_user", "mssqluser")
MSSQL_PWD = config_data.get("mssql_password", "mssqlpwd")

MSSQL_CONN_STR = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={MSSQL_SERVER},{MSSQL_PORT};"
    f"DATABASE={MSSQL_DB};"
    f"UID={MSSQL_USER};"
    f"PWD={MSSQL_PWD};"
    f"Encrypt=no;"
    f"TrustServerCertificate=yes;"
)

# ---------------------------------------------------------
# CONFIGURACIÓN MQTT
# ---------------------------------------------------------
MQTT_HOST = config_data.get("mqtt_host", "core-mosquitto")
MQTT_PORT = config_data.get("mqtt_port", 1883)
MQTT_USER = config_data.get("mqtt_user", "")
MQTT_PWD = config_data.get("mqtt_password", "")
MQTT_ID = config_data.get("mqtt_id", "mqtt2mssqlid")
MQTT_TOPIC = config_data.get("mqtt_topic", "mqtt2mssql/query")

# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
LOG_LEVEL = config_data.get("log_level", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ---------------------------------------------------------
# EVENT LOOP GLOBAL
# ---------------------------------------------------------
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ---------------------------------------------------------
# COLA FIFO
# ---------------------------------------------------------
queue = asyncio.Queue()

# ---------------------------------------------------------
# WORKER SQL
# ---------------------------------------------------------
async def worker_sql(pool):
    while True:
        query_text = await queue.get()
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_text)
                    logging.info(f"SQL ejecutado correctamente: {query_text}")
        except Exception as e:
            logging.error(f"Error ejecutando SQL: {e}")
        finally:
            queue.task_done()

# ---------------------------------------------------------
# PROCESAR MENSAJE MQTT
# ---------------------------------------------------------
def on_message(client, userdata, msg):
    try:
        query = msg.payload.decode("utf-8").strip()

        if not query.endswith(";"):
            query += ";"

        logging.info(f"MQTT recibido → {query}")

        asyncio.run_coroutine_threadsafe(queue.put(query), loop)

    except Exception as e:
        logging.error(f"Error procesando mensaje MQTT: {e}")

# ---------------------------------------------------------
# MQTT CLIENT
# ---------------------------------------------------------
def iniciar_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, MQTT_ID)

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PWD)

    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC)

    client.loop_start()
    logging.info("MQTT conectado y escuchando...")

    return client

# ---------------------------------------------------------
# MAIN ASYNC
# ---------------------------------------------------------
async def main():
    logging.info("Creando pool MSSQL...")

    try:
        pool = await asyncodbc.create_pool(
            dsn=MSSQL_CONN_STR,
            minsize=10,
            maxsize=10,
            autocommit=True
        )
    except Exception as e:
        logging.error(f"Error creando pool MSSQL: {e}")
        raise

    logging.info("Pool MSSQL creado correctamente.")

    # Lanzar workers SQL
    for _ in range(10):
        loop.create_task(worker_sql(pool))

    # Iniciar MQTT
    iniciar_mqtt()

    # Mantener el loop vivo
    while True:
        await asyncio.sleep(1)

# ---------------------------------------------------------
# EJECUCIÓN
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logging.info("Cerrando addon...")
    finally:
        loop.stop()
        loop.close()
