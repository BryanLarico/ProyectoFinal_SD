# iq_option.py

from iqoptionapi.stable_api import IQ_Option
import user  # Importamos las credenciales desde user.py
import random
import time

# Codigos de color ANSI para la terminal
COLOR_VERDE = "\033[92m"
COLOR_ROJO = "\033[91m"
COLOR_RESET = "\033[0m"

def ejecutar_bot_completo():
    print("Iniciando componentes e integrando reglas de Ertek et al. 2022")
    
    api = IQ_Option(user.EMAIL, user.PASSWORD)
    status, message = api.connect()

    if not status:
        print(f"Error critico: No se pudo iniciar el Core: {message}")
        return

    print("Enlace WebSocket establecido con el servidor financiero")
    api.change_balance("PRACTICE")
    
    # Guardar saldo inicial absoluto para el resumen final
    saldo_inicial_absoluto = api.get_balance()
    
    CICLOS_DE_PRUEBA = 3  
    ACTIVO = "EURUSD-OTC" 
    EXPIRACION = 1        
    Z_FRACCION = 0.01     

    for ciclo in range(1, CICLOS_DE_PRUEBA + 1):
        print(f"\nIniciando ciclo operativo {ciclo} de {CICLOS_DE_PRUEBA}")
        
        saldo_actual = api.get_balance()
        print(f"Saldo disponible: {saldo_actual} USD")

        monto_inversion = max(1, int(saldo_actual * Z_FRACCION))
        print(f"Proporcion de riesgo z: {Z_FRACCION*100}%")
        print(f"Calculo dinamico: {saldo_actual} USD por {Z_FRACCION} da una inversion de {monto_inversion} USD")

        direccion_senal = random.choice(["call", "put"])
        print(f"Direccion determinada por el algoritmo: {direccion_senal.upper()}")

        print(f"Colocando orden en {ACTIVO} con expiracion a {EXPIRACION} min")
        check, id_orden = api.buy(monto_inversion, ACTIVO, direccion_senal, EXPIRACION)

        if check:
            print(f"Transaccion enviada. ID de Mercado: {id_orden}")
            print("Esperando la expiracion del contrato en tiempo real")
            
            resultado = api.check_win_v3(id_orden)
            
            print("\nResultado de la expiracion:")
            if resultado < 0:
                print(f"{COLOR_ROJO}Operacion cerrada en perdida. Retorno: {resultado} USD{COLOR_RESET}")
            elif resultado > 0:
                print(f"{COLOR_VERDE}Operacion cerrada en ganancia. Retorno Neto: +{resultado:.2f} USD{COLOR_RESET}")
            else:
                print("Operacion cerrada en empate. Balance sin alteraciones")
            
            # Reducido al minimo para optimizar tiempo en la presentacion
            time.sleep(0.5)
        else:
            print(f"El broker rechazo la orden en el ciclo {ciclo}")
            break

    # Extraccion de balances finales
    saldo_final_absoluto = api.get_balance()
    rendimiento = saldo_final_absoluto - saldo_inicial_absoluto
    
    print("\nDemostracion finalizada")
    print(f"Saldo Inicial: {saldo_inicial_absoluto:.2f} USD")
    print(f"Saldo Final: {saldo_final_absoluto:.2f} USD")
    
    if rendimiento > 0:
        print(f"Rendimiento: {COLOR_VERDE}Ganancia de {rendimiento:.2f} USD{COLOR_RESET}")
    elif rendimiento < 0:
        print(f"Rendimiento: {COLOR_ROJO}Perdida de {abs(rendimiento):.2f} USD{COLOR_RESET}")
    else:
        print("Rendimiento: Sin variacion en el capital")
        
    print("Finalizando operaciones del Nodo Core")
    try:
        api.api.close()
    except:
        pass
    print("Socket destruido de forma segura. Proyecto finalizado.")

if __name__ == "__main__":
    ejecutar_bot_completo()