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

# VARIABLES GLOBAL PARA LA CONEXIÓN PERSISTENTE
conn_mssql = None
cursor_mssql = None

# VARIABLES PARA EL BUFFER SECUENCIAL
query_buffer = []
buffer_lock = threading.Lock()
MAX_BATCH_SIZE = 50          
MAX_WAIT_TIME = 1.0          
ultimo_vaciado = time.time()

def conectar_mssql_persistente():
    """Establece y mantiene viva la conexión global con SQL Server."""
    global conn_mssql, cursor_mssql
    while True:
        try:
            if conn_mssql is None:
                logging.info(f"Abriendo conexión persistente con MSSQL ({MSSQL_SERVER})...")
                # Establecemos un timeout corto de red para evitar congelamientos si el servidor cae
                conn_mssql = pyodbc.connect(CONNECTION_STRING, timeout=5)
                cursor_mssql = conn_mssql.cursor()
                logging.info("Conexión persistente establecida con éxito.")
                break
        except Exception as e:
            logging.error(f"No se pudo conectar a MSSQL. Reintentando en 5 segundos... Detalle: {e}")
            conn_mssql = None
            time.sleep(5)

def procesar_bloque_secuencial():
    """Hilo secundario de alta velocidad con conexión abierta."""
    global query_buffer, ultimo_vaciado, conn_mssql, cursor_mssql
    
    # Inicializar la conexión permanente al arrancar el hilo
    conectar_mssql_persistente()
    
    while True:
        time.sleep(0.05)  
        
        queries_a_ejecutar = []
        ahora = time.time()
        
        with buffer_lock:
            tamano_buffer = len(query_buffer)
            tiempo_transcurrido = ahora - ultimo_vaciado
            
            if tamano_buffer > 0 and (tamano_buffer >= MAX_BATCH_SIZE or tiempo_transcurrido >= MAX_WAIT_TIME):
                queries_a_ejecutar = list(query_buffer)
                query_buffer.clear()
                ultimo_vaciado = ahora
        
        if queries_a_ejecutar:
            script_sql_completo = "\n".join(queries_a_ejecutar)
            
            # Bucle de ejecución con autocuración si la conexión persistente muere
            try:
                if conn_mssql is None:
                    conectar_mssql_persistente()
                
                # Ejecuta el bloque instantáneamente (la conexión ya está abierta y logueada)
                cursor_mssql.execute(script_sql_completo)
                conn_mssql.commit()
                logging.info(f"Bloque inyectado instantáneamente: {len(queries_a_ejecutar)} consultas procesadas.")
                
            except (pyodbc.Error, Exception) as db_error:
                logging.error(f"Fallo en la inyección del bloque. Evaluando estado de la conexión... Detalle: {db_error}")
                
                # Forzar el cierre y limpieza para que el próximo ciclo reabra una conexión limpia
                try: cursor_mssql.close()
                except: pass
                try: conn_mssql.close()
                except: pass
                
                conn_mssql = None
                cursor_mssql = None
                
                # Guardamos una copia en el log para diagnóstico humano
                logging.debug(f"Script del bloque afectado:\n{script_sql_completo}")

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

# Iniciar el motor de fondo
worker_thread = threading.Thread(target=procesar_bloque_secuencial, daemon=True)
worker_thread.start()

CLIENT_ID = MQTT_ID
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
except AttributeError:
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

client.on_message = on_message

if MQTT_USER and MQTT_PWD:
    client.username_pw_set(username=MQTT_USER, password=MQTT_PWD)
    logging.info(f"Aplicando credenciales para el usuario MQTT: {MQTT_USER}")

logging.info("Iniciando puente asíncrono HÍBRIDO SECUENCIAL con Conexión Persistente...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = MQTT_TOPIC
client.subscribe(TOPICO_SQL, qos=1)
logging.info(f"Escuchando ráfagas masivas en tiempo real en: {TOPICO_SQL}")

client.loop_forever()
