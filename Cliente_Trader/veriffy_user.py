# verificar_usuario.py
# PROGRAMA 1: Modulo de Autenticacion y Validacion de Credenciales

from iqoptionapi.stable_api import IQ_Option
import user  # Importamos las credenciales desde user.py

def ejecutar_validacion():
    print(f"Intentando conectar al broker con el usuario: {user.EMAIL}...")
    
    # Inicializar la API utilizando el modulo seguro user.py
    api = IQ_Option(user.EMAIL, user.PASSWORD)
    status, message = api.connect()

    if status:
        print("\n[ÉXITO] Conexión WebSocket establecida correctamente.")
        print("El usuario y la contraseña son VALIDOS.")
        
        # Forzar modo practica por seguridad durante la demostracion
        api.change_balance("PRACTICE")
        saldo = api.get_balance()
        print(f"Estado de la cuenta de pruebas: ACTIVA (Saldo: ${saldo} USD)")
        
        # Cierre seguro adaptado a la version del fork de la comunidad
        print("Cerrando conexion de manera segura...")
        try:
            api.api.close()
        except:
            pass
        print("[INFO] Nodo desconectado.")
    else:
        print(f"\n[ERROR] Autenticacion fallida: {message}")
        print("Por favor, verifica el correo o la contraseña en user.py")

if __name__ == "__main__":
    ejecutar_validacion()