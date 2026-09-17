#!/usr/bin/env python3
import asyncio
import json
import logging
import signal
import threading

import asyncodbc
import paho.mqtt.client as mqtt


CONFIG_PATH = "/data/options.json"
NUM_WORKERS = 12
SHUTDOWN_TIMEOUT = 10
CONNECTION_ERROR_CODES = ("08S01", "HYT00", "08001", "01000")
DEADLOCK_ERROR_CODES = ("1205", "40001")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            return json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR cargando configuración {CONFIG_PATH}: {exc}")
        raise SystemExit(1) from exc


config_data = load_config()

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
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
)

MQTT_HOST = config_data.get("mqtt_host", "core-mosquitto")
MQTT_PORT = config_data.get("mqtt_port", 1883)
MQTT_USER = config_data.get("mqtt_user", "")
MQTT_PWD = config_data.get("mqtt_password", "")
MQTT_ID = config_data.get("mqtt_id", "mqtt2mssqlid")
MQTT_TOPIC = config_data.get("mqtt_topic", "mqtt2mssql/query")

configured_log_level = config_data.get("log_level", "WARNING").upper()
log_level_aliases = {"TRACE": logging.DEBUG, "NOTICE": logging.INFO}
log_level = log_level_aliases.get(
    configured_log_level,
    getattr(logging, configured_log_level, logging.WARNING),
)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def is_connection_error(error_text):
    return any(code in error_text for code in CONNECTION_ERROR_CODES)


def is_deadlock(error_text):
    return any(code in error_text for code in DEADLOCK_ERROR_CODES)


async def close_quietly(resource):
    if resource is None:
        return

    try:
        await resource.close()
    except Exception:
        pass


async def acquire_connection(pool, worker_id):
    while True:
        try:
            return await pool.acquire()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.error(
                "Worker %d: no se pudo obtener una conexión MSSQL: %s",
                worker_id,
                exc,
            )
            await asyncio.sleep(1)


async def execute_query(pool, query_text, worker_id):
    conn = await acquire_connection(pool, worker_id)
    cursor = None

    try:
        cursor = await conn.cursor()

        for attempt in range(2):
            try:
                await cursor.execute(query_text)
                logging.debug("Worker %d: SQL ejecutado correctamente", worker_id)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_text = str(exc)

                if is_deadlock(error_text) and attempt == 0:
                    logging.warning(
                        "Worker %d: deadlock detectado; reintentando la consulta",
                        worker_id,
                    )
                    await asyncio.sleep(0.1)
                    continue

                if is_connection_error(error_text):
                    logging.error(
                        "Worker %d: conexión MSSQL perdida durante la ejecución. "
                        "La consulta no se reintentará para evitar posibles duplicados. "
                        "Error: %s | Consulta fallida: %s",
                        worker_id,
                        exc,
                        query_text,
                    )
                    await close_quietly(cursor)
                    cursor = None
                    await close_quietly(conn)
                    return

                logging.error(
                    "Worker %d: error ejecutando consulta SQL: %s | "
                    "Consulta fallida: %s",
                    worker_id,
                    exc,
                    query_text,
                )
                return
    finally:
        await close_quietly(cursor)
        await pool.release(conn)


async def worker_sql(pool, queue, worker_id):
    while True:
        query_text = await queue.get()
        try:
            await execute_query(pool, query_text, worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.exception(
                "Worker %d: error inesperado procesando una consulta: %s",
                worker_id,
                exc,
            )
        finally:
            queue.task_done()


def on_message(client, userdata, msg):
    del client

    if not userdata["accepting_messages"].is_set():
        return

    try:
        query_text = msg.payload.decode("utf-8")
        if not query_text.endswith(";"):
            query_text += ";"

        logging.debug("Consulta MQTT recibida")
        userdata["loop"].call_soon_threadsafe(
            userdata["queue"].put_nowait,
            query_text,
        )
    except Exception as exc:
        logging.error("Error procesando mensaje MQTT: %s", exc)


def on_connect(client, userdata, flags, reason_code, properties):
    del userdata, flags, properties

    if getattr(reason_code, "is_failure", reason_code != 0):
        logging.error("Error conectando con MQTT: %s", reason_code)
        return

    logging.warning("MQTT conectado. Suscribiendo al topic %s", MQTT_TOPIC)
    result, _ = client.subscribe(MQTT_TOPIC, qos=0)
    if result != mqtt.MQTT_ERR_SUCCESS:
        logging.error("Error suscribiendo al topic MQTT. Código: %s", result)


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    del client, disconnect_flags, properties

    if userdata["stopping"].is_set():
        logging.info("MQTT desconectado durante el cierre")
    else:
        logging.warning(
            "MQTT desconectado (rc=%s). Se intentará reconectar automáticamente",
            reason_code,
        )


def start_mqtt(loop, queue, accepting_messages, stopping):
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_ID,
        userdata={
            "loop": loop,
            "queue": queue,
            "accepting_messages": accepting_messages,
            "stopping": stopping,
        },
    )

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PWD)

    client.on_message = on_message
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    logging.warning("Cliente MQTT iniciado; esperando conexión con el broker")
    return client


async def stop_mqtt(client):
    if client is None:
        return

    try:
        client.disconnect()
    except Exception as exc:
        logging.warning("Error desconectando MQTT durante el cierre: %s", exc)

    try:
        client.loop_stop()
    except Exception as exc:
        logging.warning("Error deteniendo el loop MQTT: %s", exc)


async def main():
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    stop_event = asyncio.Event()
    accepting_messages = threading.Event()
    stopping = threading.Event()
    accepting_messages.set()

    def request_stop(signal_name):
        if stop_event.is_set():
            return
        logging.warning("Señal %s recibida; iniciando cierre limpio", signal_name)
        accepting_messages.clear()
        stopping.set()
        stop_event.set()

    for stop_signal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            stop_signal,
            request_stop,
            stop_signal.name,
        )

    logging.warning("Creando pool MSSQL con %d conexiones", NUM_WORKERS)
    pool = await asyncodbc.create_pool(
        dsn=MSSQL_CONN_STR,
        minsize=NUM_WORKERS,
        maxsize=NUM_WORKERS,
        autocommit=True,
    )

    workers = [
        asyncio.create_task(
            worker_sql(pool, queue, worker_id),
            name=f"sql-worker-{worker_id}",
        )
        for worker_id in range(1, NUM_WORKERS + 1)
    ]
    mqtt_client = None

    try:
        mqtt_client = start_mqtt(
            loop,
            queue,
            accepting_messages,
            stopping,
        )
        logging.warning(
            "MQTT2MSSQL iniciado correctamente con %d workers SQL y TLS para MSSQL",
            NUM_WORKERS,
        )
        await stop_event.wait()
    finally:
        accepting_messages.clear()
        stopping.set()
        await stop_mqtt(mqtt_client)

        try:
            await asyncio.wait_for(queue.join(), timeout=SHUTDOWN_TIMEOUT)
        except TimeoutError:
            logging.warning(
                "Tiempo de cierre agotado; quedan %d consultas pendientes",
                queue.qsize(),
            )

        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        pool.close()
        await pool.wait_closed()
        logging.warning("MQTT2MSSQL detenido correctamente")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.exception("Error inesperado en la ejecución principal")
        raise
