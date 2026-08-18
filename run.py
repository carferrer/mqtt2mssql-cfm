import json
import paho.mqtt.client as mqtt
import pyodbc

# Configuración de MSSQL (Usa Connection Pooling nativo del driver)
# Al habilitar Pooling, pyodbc mantiene las conexiones abiertas en segundo plano
ConnectionString = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=IP_DE_TU_SERVIDOR,1433;"
    "DATABASE=TuBaseDatos;"
    "UID=TuUsuario;"
    "PWD=TuContraseña;"
    "TrustServerCertificate=yes;"
    "Pooling=True;" # <- Clave para el rendimiento
)

def ejecutar_insert_complejo(payload):
    try:
        # Convierte el mensaje MQTT (JSON) a diccionario de Python
        datos = json.loads(payload)
        
        # Abre conexión (gracias al pooling, toma una ya existente instantáneamente)
        conn = pyodbc.connect(ConnectionString)
        cursor = conn.cursor()
        
        # Aquí ejecutas tu INSERT complejo o tu Stored Procedure
        query = "EXEC TuProcedimientoComplejo @id=?, @valor=?, @fecha=?;"
        params = (datos['entity_id'], datos['state'], datos['last_changed'])
        
        cursor.execute(query, params)
        conn.commit()
        
    except Exception as e:
        print(f"Error al insertar en MSSQL: {e}")
    finally:
        cursor.close()
        conn.close() # Devuelve la conexión al pool, no la destruye

# Configuración de MQTT
def on_message(client, userdata, msg):
    # Este evento se dispara cada vez que llega un dato desde Home Assistant
    ejecutar_insert_complejo(msg.payload.decode('utf-8'))

client = mqtt.Client()
client.on_message = on_message

# Conecta al broker MQTT de tu Home Assistant (normalmente el add-on Mosquitto)
client.connect("core-mosquitto", 1883, 60)
client.subscribe("homeassistant/+/state") # O el tópico que uses

client.loop_forever()
