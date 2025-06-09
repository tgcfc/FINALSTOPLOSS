import sys
import random
import string
import time
import ccxt
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime  # Para imprimir fecha/hora en compra/venta
from binance.client import Client
from math import floor

# Variables globales para restricciones y seguimiento# Variables globales para restricciones y seguimiento\ultimo_precio_venta = None
tiempo_ultima_venta = 0
stop_price = None  # Nuevo: precio de stop loss
en_dolares = True  # Estado inicial
tiempo_espera_usd = 50  # 30 min (segundos)

# Ajusta cantidad al step_size permitido
def ajustar_cantidad(cantidad, step_size):
    return floor(cantidad / step_size) * step_size

# Claves API
API_KEY = "..."
API_SECRET = "..."
COPY_API_KEY = "..."
COPY_API_SECRET = "..."

client = Client(COPY_API_KEY, COPY_API_SECRET)
client_lead = Client(COPY_API_KEY, COPY_API_SECRET)

# Función de compra con retorno de éxito/fallo

def comprar_btc():
    global ultimo_precio_venta, tiempo_ultima_venta, stop_price
    # Restricción de recompra
    if ultimo_precio_venta is not None:
        if time.time() - tiempo_ultima_venta < 1200:
            precio_temp = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
            if precio_temp > ultimo_precio_venta:
                print("Restricción de recompra => compra cancelada.")
                return False
    # Intento de compra
    try:
        usdt_balance = float(client.get_asset_balance(asset="USDT")["free"])
        if usdt_balance <= 0:
            print("Saldo USDT insuficiente.")
            return False
        precio = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
        info = client.get_symbol_info("BTCUSDT")
        for f in info['filters']:
            if f['filterType']=='LOT_SIZE':
                step_size = float(f['stepSize']); min_qty=float(f['minQty']); break
        cantidad = ajustar_cantidad(usdt_balance/precio, step_size)
        if cantidad < min_qty:
            print("Cantidad menor al mínimo.")
            return False
        orden = client.order_market_buy(symbol="BTCUSDT", quantity=cantidad)
        print(f"Compra ejecutada: {orden}")
        # Stop loss al 0.5% abajo
        stop_price = precio * 0.995
        # Copy trading
        try:
            client_lead.order_market_buy(symbol="BTCUSDT", quantity=cantidad)
        except Exception as e:
            print(f"Copy trading buy falló: {e}")
        return True
    except Exception as e:
        print(f"Error en compra: {e}")
        return False

# Función de venta

def vender_btc():
    global ultimo_precio_venta, tiempo_ultima_venta, stop_price
    try:
        btc_balance = float(client.get_asset_balance(asset="BTC")["free"])
        if btc_balance <= 0:
            return False
        info = client.get_symbol_info("BTCUSDT")
        for f in info['filters']:
            if f['filterType']=='LOT_SIZE':
                step_size = float(f['stepSize']); min_qty=float(f['minQty']); break
        cantidad = ajustar_cantidad(btc_balance, step_size)
        if cantidad < min_qty:
            return False
        orden = client.order_market_sell(symbol="BTCUSDT", quantity=cantidad)
        # Copy trading sell
        try:
            btc_lead = float(client_lead.get_asset_balance(asset="BTC")["free"])
            qty_lead = ajustar_cantidad(btc_lead, step_size)
            if qty_lead>=min_qty:
                client_lead.order_market_sell(symbol="BTCUSDT", quantity=qty_lead)
        except Exception as e:
            print(f"Copy trading sell falló: {e}")
        # Guardar estado venta
        ultimo_precio_venta = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
        tiempo_ultima_venta = time.time()
        stop_price = None
        return True
    except Exception as e:
        print(f"Error en venta: {e}")
        return False

# Función de forecast para próximas horas (regresión lineal)
def forecast_slope(exchange, horas=3):
    ohlcv = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=horas+1)
    df = pd.DataFrame(ohlcv, columns=['ts','o','h','l','c','v'])
    closes = df['c'].values
n    x = np.arange(len(closes))
    m, _ = np.polyfit(x, closes, 1)
    return m > 0

# Integrar forecast en validación adicional

def validacion_adicional(exchange):
    # ... (todas las checks previas) ...
    # Nuevo: forecast positivo
    if not forecast_slope(exchange, horas=3):
        print("Forecast para próximas horas bajista => Bloquear compra.")
        return False
    return True

# Lógica principal

def main():
    global en_dolares, stop_price
    exchange = ccxt.binance()
    # Inicialización
    while True:
        precio0 = exchange.fetch_ticker('BTC/USDT')['last']
        if precio0: break
        time.sleep(5)
    guardado = precio0; ultima_op=time.time()
    while True:
        precio = exchange.fetch_ticker('BTC/USDT')['last']
        # Monitorear stop loss
        if not en_dolares and stop_price and precio <= stop_price:
            print(f"Stop loss alcanzado (${precio}) => Venta.")
            if vender_btc():
                en_dolares=True; guardado=precio; ultima_op=time.time()
        variacion = (precio-guardado)/guardado*100
        # Compra
        if en_dolares:
            # condiciones originales + validacion_adicional
            if validacion_adicional(exchange):
                if comprar_btc():
                    en_dolares=False; guardado=precio; ultima_op=time.time()
        else:
            # condiciones de venta originales
            if variacion>=0.5:
                if vender_btc(): en_dolares=True; guardado=precio; ultima_op=time.time()
        time.sleep(5)

if __name__=="__main__":
    main()
