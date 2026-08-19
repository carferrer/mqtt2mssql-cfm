import sys
import json
import logging
import queue
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
    f"Pooling=True;" 
)

# COLA EN MEMORIA: Mantiene el orden FIFO estricto de los mensajes
sql_queue = queue.Queue()

def trabajador_sql_secuencial():
    """Hilo único de fondo que procesa la cola UNA A UNA en orden estricto de llegada."""
    while True:
        # Se queda esperando hasta que entre una query en la cola (bloqueo eficiente de CPU)
        query_text = sql_queue.get()
        
        cursor = None
        conn = None
        try:
            conn = pyodbc.connect(CONNECTION_STRING)
            cursor = conn.cursor()
            
            cursor.execute(query_text)
            conn.commit()
            logging.info("Sentencia ejecutada individualmente en orden estricto.")
            
        except pyodbc.Error as db_error:
            logging.error("Fallo de ejecución en SQL Server (Esta fila se saltó).")
            logging.error(f"Detalle técnico: {db_error}")
            logging.error(f"Sentencia fallida:\n{query_text}")
        except Exception as e:
            logging.error(f"Error inesperado al procesar la sentencia: {e}")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            # Notifica a la cola que la tarea actual ha terminado
            sql_queue.task_done()

def on_message(client, userdata, msg, properties=None):
    """Recibe los mensajes de MQTT a la velocidad de la luz y los encola manteniendo el orden."""
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if query_recibida:
            # Coloca la query al final de la cola (Operación ultra rápida en microsegundos)
            sql_queue.put(query_recibida)
            logging.debug("Consulta guardada en la cola secuencial.")
            
    except Exception as e:
        logging.error(f"No se pudo decodificar el payload entrante de MQTT: {e}")

# Iniciar el HILO ÚNICO trabajador para procesar la base de datos de forma secuencial
worker_thread = threading.Thread(target=trabajador_sql_secuencial, daemon=True)
worker_thread.start()

CLIENT_ID = MQTT_ID
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
except AttributeError:
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

client.on_message = on_message

if MQTT_USER and MQTT_PWD:
    client.username_pw_set(username=MQTT_USER, password=MQTT_PWD)
    logging.info(f"Aplicando credenciales de autenticación para el usuario MQTT: {MQTT_USER}")

logging.info("Iniciando puente asíncrono SECUENCIAL de alto rendimiento MQTT-MSSQL...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = MQTT_TOPIC
client.subscribe(TOPICO_SQL, qos=1)
logging.info(f"Escuchando ráfagas con orden cronológico garantizado en: {TOPICO_SQL}")

client.loop_forever()
