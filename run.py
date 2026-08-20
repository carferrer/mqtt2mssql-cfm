#!/usr/bin/env python3
import asyncio
import logging
import paho.mqtt.client as mqtt
import asyncodbc
import json

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

# TLS ACTIVADO
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
# COLA FIFO
# ---------------------------------------------------------
queue = asyncio.Queue()

# ---------------------------------------------------------
# WORKER SQL CON RECONEXIÓN + REINTENTO DEADLOCK
# ---------------------------------------------------------
async def worker_sql(pool):
    conn = None
    cursor = None

    while True:
        try:
            # Crear conexión si no existe
            if conn is None:
                try:
                    conn = await pool.acquire()
                    cursor = await conn.cursor()

                    try:
                        cursor.fast_executemany = True
                    except:
                        pass

                    logging.warning("Conexión MSSQL establecida en worker")

                except Exception as e:
                    logging.error(f"Error creando conexión MSSQL: {e}")
                    conn = None
                    cursor = None
                    await asyncio.sleep(1)
                    continue

            # Obtener comando FIFO
            query_text = await queue.get()

            try:
                await cursor.execute(query_text)
                logging.debug(f"SQL OK: {query_text}")

            except Exception as e:
                err = str(e)
                logging.error(f"SQL ERROR: {err} | {query_text}")

                # Deadlock → reintentar una vez
                if "1205" in err or "40001" in err:
                    logging.warning("Deadlock detectado. Reintentando comando...")
                    await asyncio.sleep(0.1)
                    try:
                        await cursor.execute(query_text)
                        logging.warning("Deadlock resuelto en reintento.")
                    except Exception as e2:
                        logging.error(f"Error tras reintento de deadlock: {e2}")
                    finally:
                        queue.task_done()
                    continue

                # Errores de conexión reales → reconectar
                if any(code in err for code in ["08S01", "HYT00", "08001", "01000"]):
                    logging.warning("Conexión MSSQL perdida. Reconectando...")

                    try:
                        await cursor.close()
                    except:
                        pass

                    try:
                        await conn.close()
                    except:
                        pass

                    conn = None
                    cursor = None

                else:
                    logging.warning("Error SQL normal. No se reconecta.")

            finally:
                queue.task_done()

        except Exception as fatal:
            logging.error(f"Error fatal en worker: {fatal}")
            conn = None
            cursor = None
            await asyncio.sleep(1)

# ---------------------------------------------------------
# PROCESAR MENSAJE MQTT
# ---------------------------------------------------------
def on_message(client, userdata, msg):
    try:
        query = msg.payload.decode("utf-8")

        if query[-1] != ";":
            query += ";"

        logging.warning(f"MQTT recibido → {query}")

        loop.call_soon_threadsafe(queue.put_nowait, query)

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
# APAGADO LIMPIO
# ---------------------------------------------------------
async def shutdown(pool, mqtt_client):
    logging.warning("Apagando addon MQTT2MSSQL...")

    # Cerrar MQTT
    try:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        logging.warning("MQTT desconectado correctamente.")
    except Exception as e:
        logging.error(f"Error cerrando MQTT: {e}")

    # Cerrar pool MSSQL
    try:
        pool.close()
        await pool.wait_closed()
        logging.warning("Pool MSSQL cerrado correctamente.")
    except Exception as e:
        logging.error(f"Error cerrando pool MSSQL: {e}")

    # Cancelar tareas activas
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in tasks:
        t.cancel()

    logging.warning("Tareas canceladas. Addon apagado correctamente.")

# ---------------------------------------------------------
# MAIN ASYNC
# ---------------------------------------------------------
async def main():
    logging.warning("Creando pool MSSQL optimizado...")

    pool = await asyncodbc.create_pool(
        dsn=MSSQL_CONN_STR,
        minsize=6,
        maxsize=6,
        autocommit=True
    )

    logging.warning("Pool MSSQL creado correctamente.")

    # Mensaje visible en cualquier visor de logs
    logging.warning("===========================================================")
    logging.warning("   MQTT2MSSQL Add-on iniciado correctamente")
    logging.warning("   Workers SQL activos, MQTT escuchando, pool MSSQL OK")
    logging.warning("   TLS activado en la comunicación con MSSQL")
    logging.warning("===========================================================")

    # Lanzar workers SQL optimizados
    for _ in range(6):
        loop.create_task(worker_sql(pool))

    # Iniciar MQTT
    mqtt_client = iniciar_mqtt()

    # Mantener el loop vivo
    while True:
        await asyncio.sleep(1)

    return mqtt_client, pool

# ---------------------------------------------------------
# EJECUCIÓN
# ---------------------------------------------------------
if __name__ == "__main__":
    mqtt_client = None
    pool = None

    try:
        mqtt_client, pool = loop.run_until_complete(main())
    except KeyboardInterrupt:
        logging.warning("Recibido SIGTERM desde Home Assistant.")
    finally:
        loop.run_until_complete(shutdown(pool, mqtt_client))
        loop.stop()
        loop.close()
        logging.warning("Addon detenido sin errores.")
