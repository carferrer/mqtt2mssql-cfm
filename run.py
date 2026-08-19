import sys
import json
import logging
import queue
import threading
import time
import paho.mqtt.client as mqtt
import pymssql

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

# Cola secuencial FIFO en memoria RAM para asegurar el orden estricto de llegada
query_queue = queue.Queue()

# Frecuencia de vaciado a 100ms para fulminar la latencia de Node-RED
MICRO_BATCH_INTERVAL = 0.1  
MAX_BATCH_SIZE = 100

conn_mssql = None

def conectar_mssql_tds():
    """Establece una conexión directa por socket TCP/IP con protocolo TDS."""
    global conn_mssql
    while True:
        try:
            if conn_mssql is None:
                logging.info(f"Abriendo socket TDS directo con MSSQL ({MSSQL_SERVER})...")
                conn_mssql = pymssql.connect(
                    server=MSSQL_SERVER,
                    port=int(MSSQL_PORT),
                    user=MSSQL_USER,
                    password=MSSQL_PWD,
                    database=MSSQL_DB,
                    autocommit=False, # Controlamos la red mediante confirmación diferida de ráfagas
                    login_timeout=5
                )
                logging.info("Tubería TDS de alta velocidad establecida.")
                break
        except Exception as e:
            logging.error(f"Fallo en socket TDS. Reintentando en 5s... Detalle: {e}")
            conn_mssql = None
            time.sleep(5)

def despachador_mssql_loop():
    """Hilo de fondo que procesa los micro-lotes encapsulados en bloques TRY/CATCH nativos."""
    global conn_mssql
    conectar_mssql_tds()
    
    while True:
        time.sleep(MICRO_BATCH_INTERVAL)
        
        lote_queries = []
        while not query_queue.empty() and len(lote_queries) < MAX_BATCH_SIZE:
            try:
                query = query_queue.get_nowait()
                lote_queries.append(query)
            except queue.Empty:
                break
        
        if lote_queries:
            # Encapsulado inteligente: Protegemos cada query en un bloque TRY/CATCH nativo de SQL Server.
            # Si una consulta falla, avisa en el log pero permite que las demás del bloque se guarden con éxito.
            queries_protegidas = [
                f"BEGIN TRY {q} END TRY BEGIN CATCH PRINT 'Error en sentencia: ' + ERROR_MESSAGE(); END CATCH" 
                for q in lote_queries
            ]
            script_completo = "SET NOCOUNT ON;\n" + "\n".join(queries_protegidas)
            
            try:
                if conn_mssql is None:
                    conectar_mssql_tds()
                
                with conn_mssql.cursor() as cursor:
                    cursor.execute(script_completo)
                    conn_mssql.commit()
                
                logging.info(f"Ráfaga TDS procesada con éxito: {len(lote_queries)} consultas evaluadas.")
                
                for _ in lote_queries:
                    query_queue.task_done()
                    
            except Exception as db_error:
                logging.error(f"Error de red crítico en el socket TDS: {db_error}")
                logging.debug(f"Script del bloque afectado:\n{script_completo}")
                
                try: conn_mssql.rollback()
                except: pass
                conn_mssql = None
                
                for _ in lote_queries:
                    query_queue.task_done()

def on_message(client, userdata, msg, properties=None):
    """Captura los mensajes de MQTT a la velocidad de la luz y mantiene la fila india FIFO."""
    try:
        query_recibida = msg.payload.decode('utf-8').strip()
        if query_recibida:
            if not query_recibida.endswith(';'):
                query_recibida += ';'
            
            query_queue.put(query_recibida)
            logging.debug("Consulta guardada en el buffer FIFO.")
    except Exception as e:
        logging.error(f"Error al procesar mensaje MQTT: {e}")

# Iniciar el despachador secuencial de fondo
worker_thread = threading.Thread(target=despachador_mssql_loop, daemon=True)
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

logging.info("Iniciando puente de rendimiento extremo por socket nativo TDS (Cero ODBC)...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = MQTT_TOPIC
client.subscribe(TOPICO_SQL, qos=1)
logging.info(f"Escuchando ráfagas ordenadas tolerantes a fallos en: {TOPICO_SQL}")

client.loop_forever()
