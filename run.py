#!/usr/bin/env python3
import asyncio
import logging
import paho.mqtt.client as mqtt
import pyodbc
import json

# ---------------------------------------------------------
# CARGAR CONFIGURACIÓN DEL ADD-ON
# ---------------------------------------------------------
CONFIG_PATH = "/data/options.json"

try:
    with open(CONFIG_PATH, "r") as f:
        config_data = json.load(f)
except Exception as e:
    logging.debug(f"ERROR cargando configuración {CONFIG_PATH}: {e}")
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
    f"Encrypt=yes;"
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
LOG_LEVEL = config_data.get("log_level", "WARNING").upper()

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
# COLA FIFO GRANDE
# ---------------------------------------------------------
queue = asyncio.Queue(maxsize=10000)

# Tamaño de batch y tiempo máximo de espera
BATCH_SIZE = 200        # nº máximo de mensajes por lote
BATCH_TIMEOUT = 0.05    # segundos máximo que espera para completar lote

# ---------------------------------------------------------
# WORKER SQL CON BATCHING
# ---------------------------------------------------------
async def worker_sql(worker_id: int):
    conn = None
    cursor = None
    backoff = 1

    while True:
        try:
            if conn is None:
                try:
                    conn = pyodbc.connect(MSSQL_CONN_STR, timeout=5)
                    cursor = conn.cursor()
                    try:
                        cursor.fast_executemany = True
                    except:
                        pass
                    logging.info(f"[Worker {worker_id}] Conexión MSSQL establecida")
                    backoff = 1
                except Exception as e:
                    logging.error(f"[Worker {worker_id}] Error conectando MSSQL: {e}")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue

            # Construir un batch
            batch = []
            try:
                # Primer mensaje (bloqueante)
                query_text = await queue.get()
                batch.append(query_text)

                # Intentar completar el batch sin bloquear demasiado
                start = loop.time()
                while len(batch) < BATCH_SIZE and (loop.time() - start) < BATCH_TIMEOUT:
                    try:
                        q = queue.get_nowait()
                        batch.append(q)
                    except asyncio.QueueEmpty:
                        await asyncio.sleep(0.001)
                        break
            except Exception as e:
                logging.error(f"[Worker {worker_id}] Error obteniendo batch: {e}")
                continue

            # Aquí tienes un batch de N consultas (strings)
            # Estrategia simple: concatenar todas las sentencias en un solo comando
            # IMPORTANTE: esto asume que cada query_text es una sentencia completa terminada en ';'
            sql_batch = "\n".join(batch)

            try:
                cursor.execute(sql_batch)
                conn.commit()
                logging.debug(f"[Worker {worker_id}] Batch OK ({len(batch)} consultas)")
            except Exception as e:
                err = str(e)
                logging.error(f"[Worker {worker_id}] SQL ERROR en batch: {err}")

                # Deadlock → reintentar una vez el batch completo
                if "1205" in err or "40001" in err:
                    logging.warning(f"[Worker {worker_id}] Deadlock en batch. Reintentando...")
                    await asyncio.sleep(0.1)
                    try:
                        cursor.execute(sql_batch)
                        conn.commit()
                        logging.warning(f"[Worker {worker_id}] Deadlock resuelto en batch.")
                    except Exception as e2:
                        logging.error(f"[Worker {worker_id}] Error tras reintento de batch: {e2}")
                else:
                    # Errores de conexión → reconectar
                    if any(code in err for code in ["08S01", "HYT00", "08001", "01000"]):
                        logging.warning(f"[Worker {worker_id}] Conexión MSSQL perdida. Reconectando...")
                        try:
                            cursor.close()
                        except:
                            pass
                        try:
                            conn.close()
                        except:
                            pass
                        conn = None
                        cursor = None
                    else:
                        logging.warning(f"[Worker {worker_id}] Error SQL normal en batch.")

            finally:
                # Marcar todos los mensajes del batch como procesados
                for _ in batch:
                    queue.task_done()

        except Exception as fatal:
            logging.error(f"[Worker {worker_id}] Error fatal: {fatal}")
            conn = None
            cursor = None
            await asyncio.sleep(1)

# ---------------------------------------------------------
# PROCESAR MENSAJE MQTT
# ---------------------------------------------------------
def on_message(client, userdata, msg):
    try:
        query = msg.payload.decode("utf-8")

        if not query.endswith(";"):
            query += ";"

        logging.info(f"MQTT recibido → {query}")

        def push():
            try:
                queue.put_nowait(query)
            except asyncio.QueueFull:
                logging.warning("Cola llena, reintentando en 50ms...")
                loop.call_later(0.05, push)

        loop.call_soon_threadsafe(push)

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
    client.subscribe(MQTT_TOPIC, qos=0)

    client.loop_start()
    logging.warning("MQTT conectado y escuchando...")

    return client

# ---------------------------------------------------------
# MAIN ASYNC
# ---------------------------------------------------------
async def main():
    logging.warning("===========================================================")
    logging.warning("   MQTT2MSSQL Add-on iniciado (batching extremo)")
    logging.warning(f"   BATCH_SIZE={BATCH_SIZE}, BATCH_TIMEOUT={BATCH_TIMEOUT}s")
    logging.warning("===========================================================")

    # Ajusta el nº de workers según la potencia de tu MSSQL
    for i in range(10):
        loop.create_task(worker_sql(i))

    mqtt_client = iniciar_mqtt()

    await asyncio.Event().wait()
    return mqtt_client

# ---------------------------------------------------------
# EJECUCIÓN
# ---------------------------------------------------------
if __name__ == "__main__":
    mqtt_client = None
    try:
        mqtt_client = loop.run_until_complete(main())
    except Exception as e:
        logging.error(f"Error inesperado en ejecución principal: {e}")
    finally:
        logging.warning("Cerrando MQTT...")
        try:
            if mqtt_client is not None:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
        except:
            pass
        logging.warning("Add-on detenido correctamente.")
