import sys
import json
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

# Extraer las credenciales dinámicas de la configuración
MSSQL_SERVER = config_data.get("mssql_server")
MSSQL_PORT = config_data.get("mssql_port", 1433)
MSSQL_DB = config_data.get("mssql_database")
MSSQL_USER = config_data.get("mssql_user")
MSSQL_PWD = config_data.get("mssql_password")

MQTT_HOST = config_data.get("mqtt_host", "core-mosquitto")
MQTT_PORT = config_data.get("mqtt_port", 1883)

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
        # Abre o reutiliza una conexión del pool
        conn = pyodbc.connect(CONNECTION_STRING)
        cursor = conn.cursor()
        
        # Ejecuta la sentencia SQL tal y como viene de Home Assistant
        cursor.execute(query_text)
        conn.commit()
        print(f"[INFO] Sentencia ejecutada con éxito.")
        
    except pyodbc.Error as db_error:
        # Si la sentencia falla, formatea el error de forma muy visible en el registro del Add-on
        print("\n" + "="*50, file=sys.stderr)
        print(f"[ERROR MSSQL] Error de sintaxis o ejecución en SQL Server.", file=sys.stderr)
        print(f"[DETALLE DEL ERROR] {db_error}", file=sys.stderr)
        print(f"[SENTENCIA FALLIDA]\n{query_text}", file=sys.stderr)
        print("="*50 + "\n", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR INESPERADO] {e}", file=sys.stderr)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def on_message(client, userdata, msg):
    """Se ejecuta cada vez que llega una sentencia por MQTT."""
    try:
        # Decodifica el payload MQTT directamente a texto plano (tu consulta SQL)
        query_recibida = msg.payload.decode('utf-8').strip()
        
        if query_recibida:
            ejecutar_sql_puro(query_recibida)
            
    except Exception as e:
        print(f"[ERROR MQTT] No se pudo decodificar el mensaje: {e}", file=sys.stderr)

# Configuración del cliente MQTT con ID fijo y sesión persistente
CLIENT_ID = "ha_mssql_bridge_addon"
client = mqtt.Client(client_id=CLIENT_ID, clean_session=False)
client.on_message = on_message

print("[INFO] Iniciando el puente HA-MSSQL con credenciales dinámicas...")
print(f"[INFO] Conectando al bróker MQTT ({MQTT_HOST}:{MQTT_PORT})...")
client.connect(MQTT_HOST, MQTT_PORT, 60)

TOPICO_SQL = "homeassistant/mssql/execute"
# qos=1 para asegurar que no se pierda ninguna sentencia si el add-on parpadea
client.subscribe(TOPICO_SQL, qos=1)
print(f"[INFO] Conectando a MSSQL en el servidor: {MSSQL_SERVER}:{MSSQL_PORT}")
print(f"[INFO] Add-on listo y escuchando sentencias SQL puras en: {TOPICO_SQL}")

client.loop_forever()
