import sys
import json
import logging
import threading
import time
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

conn_mssql = None
cursor_mssql = None

query_buffer = []
buffer_lock = threading.Lock()
INTERVALO_VACIADO = 1.0  # Mantenemos el vaciado cada 1.0 segundo exacto
timer_activo = None

def conectar_mssql_persistente():
    global conn_mssql, cursor_mssql
    try:
        if conn_mssql is None:
            logging.info(f"Abriendo conexión persistente con MSSQL ({MSSQL_SERVER})...")
            conn_mssql = pyodbc.connect(CONNECTION_STRING, timeout=5)
            cursor_mssql = conn_mssql.cursor()
            logging.info("Conexión persistente establecida con éxito.")
    except Exception as e:
        logging.error(f"Error de conexión a MSSQL: {e}")
        conn_mssql = None
        cursor_mssql = None

def programar_proximo_vaciado():
    global timer_activo
    timer_activo = threading.Timer(INTERVALO_VACIADO, vaciar_buffer_a_mssql)
    timer_activo.daemon = True
    timer_activo.start()

def vaciar_buffer_a_mssql():
    global query_buffer, conn_mssql, cursor_mssql
    
    queries_a_ejecutar = []
    with buffer_lock:
        if query_buffer:
            queries_a_ejecutar = list(query_buffer)
            query_buffer.clear()
            
    if queries_a_ejecutar:
        # OPTIMIZACIÓN CLAVE: Iniciamos el bloque con SET NOCOUNT ON para apagar 
        # las respuestas de conteo que saturan los hilos de red de MSSQL
        script_sql_completo = "SET NOCOUNT ON;\n" + "\n".join(queries_a_ejecutar)
        
        try:
            if conn_mssql is None:
                conectar_mssql_persistente()
                
            if conn_mssql:
                cursor_mssql.execute(script_sql_completo)
                conn_mssql.commit()
                logging.info(f"Bloque inyectado de forma eficiente: {len(queries_a_ejecutar)} consultas procesadas.")
        except Exception as db_error:
            logging.error(f"Fallo en la inyección del bloque: {db_error}")
            try: cursor_mssql.close()
            except: pass
            try: conn_mssql.close()
            except: pass
            conn_mssql = None
            cursor_mssql = None
            logging.debug(f"Script del bloque afectado:\n{script_sql_completo}")

    programar_proximo_vaciado()

def on_message(client, userdata, msg, properties=None):
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if query_recibida:
            if not query_recibida.endswith(';'):
                query_recibida += ';'
                
            with buffer_lock:
                query_buffer.append(query_recibida)
            logging.debug("Sentencia guardada en el buffer ordenado.")
    except Exception as e:
        logging.error(f"No se pudo decodificar el payload de MQTT: {e}")

conectar_mssql_persistente()
programar_proximo_vaciado()

CLIENT_ID = MQTT_ID
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
except AttributeError:
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

client.on_message = on_message

if MQTT_USER and MQTT_PWD:
    client.username_pw_set(username=MQTT_USER, password=MQTT_PWD)
    logging.info(f"Aplicando credenciales para el usuario MQTT: {MQTT_USER}")

logging.info("Iniciando puente asíncrono POR EVENTOS optimizado para BBDD...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = MQTT_TOPIC
client.subscribe(TOPICO_SQL, qos=1)
logging.info(f"Escuchando ráfagas masivas en: {TOPICO_SQL}")

client.loop_forever()
