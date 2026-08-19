#!/usr/bin/env python3
import asyncio
import logging
import paho.mqtt.client as mqtt
import asyncodbc
import os

# ---------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------
MQTT_HOST = os.getenv("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "mqtt2mssql/query")
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

MSSQL_CONN_STR = os.getenv(
    "MSSQL_CONN",
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=192.168.1.100,1433;"
    "DATABASE=MiBase;"
    "UID=sa;"
    "PWD=MiPassword;"
    "Encrypt=no;"
)

POOL_SIZE = 10

# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ---------------------------------------------------------
# EVENT LOOP GLOBAL (SOLUCIÓN AL ERROR)
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

        # Enviar tarea al event loop principal
        asyncio.run_coroutine_threadsafe(queue.put(query), loop)

    except Exception as e:
        logging.error(f"Error procesando mensaje MQTT: {e}")

# ---------------------------------------------------------
# MQTT CLIENT
# ---------------------------------------------------------
def iniciar_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "mqtt2mssqlid")

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

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

    pool = await asyncodbc.create_pool(
        dsn=MSSQL_CONN_STR,
        minsize=POOL_SIZE,
        maxsize=POOL_SIZE,
        autocommit=True
    )

    logging.info(f"Pool MSSQL creado con {POOL_SIZE} conexiones.")

    # Lanzar workers SQL
    for _ in range(POOL_SIZE):
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
