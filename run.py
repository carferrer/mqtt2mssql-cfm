import sys
import json
import logging
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
)

def ejecutar_sql_puro(query_text):
    """Ejecuta la query de texto plano recibida y gestiona los errores en el log."""
    cursor = None
    conn = None
    try:
        # Este registro detallado solo se pintará en pantalla si el usuario activa el nivel DEBUG
        logging.debug(f"Procesando sentencia SQL entrante:\n{query_text}")
        
        # Abre o reutiliza una conexión del pool
        conn = pyodbc.connect(CONNECTION_STRING)
        cursor = conn.cursor()
        
        # Ejecuta la sentencia SQL tal y como viene de Home Assistant
        cursor.execute(query_text)
        conn.commit()
        logging.info("Sentencia ejecutada con éxito en SQL Server.")
        
    except pyodbc.Error as db_error:
        # Los errores críticos se reportan siempre de forma estructurada
        logging.error("Error de sintaxis o ejecución en SQL Server.")
        logging.error(f"Detalle técnico de MSSQL: {db_error}")
        logging.error(f"Sentencia fallida originaria:\n{query_text}")
    except Exception as e:
        logging.error(f"Error inesperado en la infraestructura del controlador: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def on_message(client, userdata, msg, properties=None):
    """Se ejecuta cada vez que llega una sentencia por MQTT."""
    try:
        # Decodifica el payload MQTT directamente a texto plano (tu consulta SQL)
        query_recibida = msg.payload.decode('utf-8').strip()
        
        if query_recibida:
            ejecutar_sql_puro(query_recibida)
            
    except Exception as e:
        logging.error(f"No se pudo decodificar el payload entrante de MQTT: {e}")

# Configuración del cliente MQTT con ID fijo y sesión persistente
CLIENT_ID = MQTT_ID

try:
    # Usamos la API v2 oficial moderna para eliminar el DeprecationWarning
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID, clean_session=False)
except AttributeError:
    # Fallback de seguridad por si acaso
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)

client.on_message = on_message

# ==========================================
# CONFIGURAR CREDENCIALES MQTT
# ==========================================
if MQTT_USER and MQTT_PWD:
    client.username_pw_set(username=MQTT_USER, password=MQTT_PWD)
    logging.info(f"Aplicando credenciales de autenticación para el usuario MQTT: {MQTT_USER}")

logging.info("Iniciando el puente HA-MSSQL con credenciales dinámicas y logging profesional...")
logging.info(f"Conectando al bróker MQTT ({MQTT_HOST}:{MQTT_PORT})...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = MQTT_TOPIC
# qos=1 para asegurar que no se pierda ninguna sentencia si el add-on parpadea
client.subscribe(TOPICO_SQL, qos=1)
logging.info(f"Conectando a MSSQL en el servidor de destino: {MSSQL_SERVER}:{MSSQL_PORT}")
logging.info(f"Add-on completamente operativo. Escuchando consultas SQL puras en: {TOPICO_SQL}")

client.loop_forever()
