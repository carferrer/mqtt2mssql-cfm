import sys
import json
import logging
import threading
import time
import paho.mqtt.client as mqtt
import pyodbc

# Ruta oficial donde Home Assistant guarda las opciones de la interfaz del Add-on
CONFIG_PATH = "/data/options.json"

try:
    with open(CONFIG_PATH, "r") as f:
        config_data = json.load(f)
except Exception as e:
    print(f"[CRITICAL] No se pudo leer la configuración del Add-on: {e}", file=sys.stderr)
    sys.exit(1)

# Extraer el nivel de log configurado por el usuario (por defecto INFO)
LOG_LEVEL = config_data.get("log_level", "INFO").upper()

# Configurar el formato profesional de los logs para Home Assistant
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# Extraer las credenciales dinámicas de la configuración
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

# Construcción de la cadena de conexión con las variables del Add-on
CONNECTION_STRING = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={MSSQL_SERVER},{MSSQL_PORT};"
    f"DATABASE={MSSQL_DB};"
    f"UID={MSSQL_USER};"
    f"PWD={MSSQL_PWD};"
    f"TrustServerCertificate=yes;"
    f"Pooling=True;"  # Asegura la reutilización interna de conexiones
)

# VARIABLES PARA EL BUFFER INTERNO (THREAD-SAFE)
query_buffer = []
buffer_lock = threading.Lock()
MAX_BATCH_SIZE = 100        # Número máximo de queries antes de vaciar el buffer
MAX_WAIT_TIME = 2.0         # Tiempo máximo en segundos para esperar antes de vaciar el buffer
ultimo_vaciado = time.time() # Almacena la marca de tiempo del último procesamiento

def procesar_lote_sql():
    """Hilo secundario que monitoriza el buffer y ejecuta las queries agrupadas en un solo lote."""
    global query_buffer, ultimo_vaciado
    
    while True:
        time.sleep(0.1)  # Revisa las condiciones del buffer 10 veces por segundo (alta velocidad)
        
        queries_a_ejecutar = []
        ahora = time.time()
        
        with buffer_lock:
            tamano_buffer = len(query_buffer)
            tiempo_transcurrido = ahora - ultimo_vaciado
            
            # Se procesa si se alcanza el tamaño máximo O si se supera el tiempo límite de espera
            if tamano_buffer > 0 and (tamano_buffer >= MAX_BATCH_SIZE or tiempo_transcurrido >= MAX_WAIT_TIME):
                queries_a_ejecutar = list(query_buffer)
                query_buffer.clear()
                ultimo_vaciado = ahora
        
        if queries_a_ejecutar:
            cursor = None
            conn = None
            try:
                logging.debug(f"Iniciando inserción en lote de {len(queries_a_ejecutar)} sentencias...")
                conn = pyodbc.connect(CONNECTION_STRING)
                cursor = conn.cursor()
                
                # Unificamos todas las queries del lote en una sola transacción masiva
                cursor.execute("BEGIN TRANSACTION;")
                for query in queries_a_ejecutar:
                    cursor.execute(query)
                cursor.execute("COMMIT;")
                
                logging.info(f"Lote masivo ejecutado con éxito: {len(queries_a_ejecutar)} sentencias procesadas.")
                
            except pyodbc.Error as db_error:
                if cursor:
                    try:
                        cursor.execute("ROLLBACK;")
                        logging.warning("Se realizó un ROLLBACK del lote debido a un error de base de datos.")
                    except:
                        pass
                logging.error(f"Fallo al ejecutar lote en SQL Server. Detalle técnico: {db_error}")
                logging.debug(f"Sentencias del lote fallido: {queries_a_ejecutar}")
            except Exception as e:
                logging.error(f"Error inesperado en el hilo del procesador de lotes: {e}")
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()

def on_message(client, userdata, msg, properties=None):
    """Recibe los mensajes de MQTT a la velocidad de la luz y los mete al buffer de memoria RAM."""
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if query_recibida:
            with buffer_lock:
                query_buffer.append(query_recibida)
                
            logging.debug("Sentencia guardada en el buffer de memoria.")
            
    except Exception as e:
        logging.error(f"No se pudo decodificar el payload entrante de MQTT: {e}")

# Iniciar el hilo de procesamiento de fondo de la base de datos
worker_thread = threading.Thread(target=procesar_lote_sql, daemon=True)
worker_thread.start()

# Configuración del cliente MQTT con ID fijo y sesión persistente
CLIENT_ID = MQTT_ID
try:
    # Usamos la API v2 oficial moderna para eliminar el DeprecationWarning
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
except AttributeError:
    # Fallback de seguridad por si acaso
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

client.on_message = on_message

# Configurar credenciales de autenticación si existen
if MQTT_USER and MQTT_PWD:
    client.username_pw_set(username=MQTT_USER, password=MQTT_PWD)
    logging.info(f"Aplicando credenciales de autenticación para el usuario MQTT: {MQTT_USER}")

logging.info("Iniciando puente de alto rendimiento MQTT-MSSQL por lotes...")
logging.info(f"Conectando al bróker MQTT ({MQTT_HOST}:{MQTT_PORT})...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = MQTT_TOPIC
# qos=1 para asegurar que no se pierda ninguna sentencia si el add-on parpadea
client.subscribe(TOPICO_SQL, qos=1)
logging.info(f"Conectando a MSSQL en el servidor de destino: {MSSQL_SERVER}:{MSSQL_PORT}")
logging.info(f"Add-on completamente operativo. Escuchando ráfagas masivas en: {TOPICO_SQL}")

client.loop_forever()
