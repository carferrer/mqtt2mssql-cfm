import sys
import json
import logging
import threading
import paho.mqtt.client as mqtt
import pyodbc

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

# OBJETO DE BLOQUEO PARA EVITAR QUE LOS EVENTOS MQTT PIBEN EL CURSOR
db_lock = threading.Lock()
conn_mssql = None
cursor_mssql = None

def conectar_mssql_persistente():
    """Establece la conexión única global al arrancar."""
    global conn_mssql, cursor_mssql
    try:
        if conn_mssql is None:
            logging.info(f"Abriendo conexión persistente con MSSQL ({MSSQL_SERVER})...")
            conn_mssql = pyodbc.connect(CONNECTION_STRING, timeout=5)
            # Desactivamos el autocommit para que pyodbc gestione las transacciones individuales rápido
            conn_mssql.autocommit = True
            cursor_mssql = conn_mssql.cursor()
            logging.info("Conexión persistente establecida y lista para ráfagas.")
    except Exception as e:
        logging.error(f"Error crítico de conexión inicial a MSSQL: {e}")
        conn_mssql = None
        cursor_mssql = None

def on_message(client, userdata, msg, properties=None):
    """Procesa cada mensaje de forma individual al instante a través de la tubería abierta."""
    global conn_mssql, cursor_mssql
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if not query_recibida:
            return

        # Aseguramos el formato
        if not query_recibida.endswith(';'):
            query_recibida += ';'

        # Sincronizamos el acceso al cursor único abierto para que las queries entren en fila india perfecta
        with db_lock:
            # Si por algún motivo la conexión se cayó, la reabrimos en el acto
            if conn_mssql is None:
                conectar_mssql_persistente()
            
            if conn_mssql:
                cursor_mssql.execute(query_recibida)
                logging.info("Consulta ejecutada con éxito a través de la tubería abierta.")

    except pyodbc.Error as db_error:
        logging.error(f"Fallo de ejecución en SQL Server (Fila saltada): {db_error}")
        logging.debug(f"Query afectada:\n{query_recibida}")
        
        # Si el error es de desconexión, limpiamos las variables para forzar reconexión en el próximo mensaje
        if "08S01" in str(db_error) or "link failure" in str(db_error).lower():
            logging.warning("Detectada caída de red con MSSQL. Forzando reinicio de tubería...")
            try: cursor_mssql.close()
            except: pass
            try: conn_mssql.close()
            except: pass
            conn_mssql = None
            cursor_mssql = None

    except Exception as e:
        logging.error(f"Error inesperado al procesar el mensaje MQTT: {e}")

# Arrancar la conexión persistente antes de encender MQTT
conectar_mssql_persistente()

CLIENT_ID = MQTT_ID
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
except AttributeError:
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

client.on_message = on_message

if MQTT_USER and MQTT_PWD:
    client.username_pw_set(username=MQTT_USER, password=MQTT_PWD)
    logging.info(f"Aplicando credenciales para el usuario MQTT: {MQTT_USER}")

logging.info("Iniciando puente asíncrono DIRECTO de alta velocidad...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = MQTT_TOPIC
client.subscribe(TOPICO_SQL, qos=1)
logging.info(f"Escuchando ráfagas individuales en tiempo real en: {TOPICO_SQL}")

client.loop_forever()
