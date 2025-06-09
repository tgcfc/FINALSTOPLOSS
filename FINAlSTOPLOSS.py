print("GitHub")
import sys
import random
import string
import time
import ccxt
import requests
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime  # Para imprimir fecha/hora en compra/venta
from binance.client import Client
from math import floor

# [NUEVO] Variables globales para restringir recompra
ultimo_precio_venta = None
tiempo_ultima_venta = 0

# [NUEVO] Variables globales para Stop-Loss
stop_loss_activado = True     # Puedes poner en False para desactivar
stop_loss_percent = 0.98      # 0.98 = venta si baja más de 2% desde la compra
precio_stop_loss = None       # Precio activador

def ajustar_cantidad(cantidad, step_size):
    """
    Ajusta una cantidad al múltiplo permitido por Binance (step_size).
    """
    return floor(cantidad / step_size) * step_size

# Tus claves Spot originales (o las que ya usabas)
API_KEY = "wNmoR7nXAk2rNR5KjqeeKPfF7sEWeQFCgzjFqSLvMYEsqI3T4LEw4R0Q9TtjhBTV"
API_SECRET = "EQG2eGIdB4ibN0ua4vlTTqSqlGIvcxK2wsoif5k6Ch0DyLFgnBJ3z6Vv6dvMSZnC"
client = Client(API_KEY, API_SECRET)

# [NUEVO] Claves para la billetera Líder (Copy Trading)
COPY_API_KEY = "Xb4SIWG5FzQR5fAzTcRigalhughRm5u3uovVCWSidOIcMzpV78KXXO7hezrY53Hq"
COPY_API_SECRET = "yBbmeWOjc70SbGwNYcNuspnUw5gMfe7uIKmd9eO1N5EvIejhLz0x4W9ezci0RXqT"
client_lead = Client(COPY_API_KEY, COPY_API_SECRET)
# Nuevas claves API para el líder de trading
COPY_API_KEY = "Xb4SIWG5FzQR5fAzTcRigalhughRm5u3uovVCWSidOIcMzpV78KXXO7hezrY53Hq"
COPY_API_SECRET = "yBbmeWOjc70SbGwNYcNuspnUw5gMfe7uIKmd9eO1N5EvIejhLz0x4W9ezci0RXqT"
# Inicializar el cliente de Binance con las nuevas claves
client = Client(COPY_API_KEY, COPY_API_SECRET)

def comprar_btc():
    """
    Compra BTC usando todo el saldo disponible en USDT.
    """
    try:
        global ultimo_precio_venta
        global tiempo_ultima_venta
        global precio_stop_loss

        # [NUEVO] Restricción de recompra (ya existía en tu código; no se toca)
        if ultimo_precio_venta is not None:
            tiempo_desde_venta = time.time() - tiempo_ultima_venta
            if tiempo_desde_venta < 1200:  # 20 min
                symbol = "BTCUSDT"
                ticker_temp = client.get_symbol_ticker(symbol=symbol)
                btc_price_temp = float(ticker_temp["price"])
                if btc_price_temp > ultimo_precio_venta:
                    print("Restricción de recompra: han pasado menos de 20 min y el precio está por encima de la última venta. Se bloquea la compra.")
                    return

        # --- CÓDIGO ORIGINAL (NO SE MODIFICA) ---
        usdt_balance = float(client.get_asset_balance(asset="USDT")["free"])

        """
            Compra BTC usando todo el saldo disponible en USDT en la cuenta de líder de trading.
            """
        try:
            # Obtener saldo disponible en USDT
            usdt_balance = float(client.get_asset_balance(asset="USDT")["free"])
            print(f"Saldo disponible en USDT: {usdt_balance}")

            if usdt_balance <= 0:
                print("Saldo insuficiente en USDT para realizar la compra.")
                return

            # Obtener el precio actual de BTC/USDT
            symbol = "BTCUSDT"
            ticker = client.get_symbol_ticker(symbol=symbol)
            btc_price = float(ticker["price"])
            print(f"Precio actual de BTC/USDT: {btc_price}")

            # [NUEVO] Guardar precio de compra para Stop-Loss
            global stop_loss_activado, stop_loss_percent
            if stop_loss_activado:
                precio_stop_loss = btc_price * stop_loss_percent
                print(f"[STOP-LOSS] Activado: Se venderá si baja de {precio_stop_loss:.2f}")

            # Obtener LOT_SIZE dinámicamente
            exchange_info = client.get_symbol_info(symbol)
            for filtro in exchange_info["filters"]:
                if filtro["filterType"] == "LOT_SIZE":
                    min_qty = float(filtro["minQty"])
                    step_size = float(filtro["stepSize"])
                    break

            # Calcular la cantidad de BTC a comprar
            btc_amount = usdt_balance / btc_price

            # Ajustar al step_size permitido
            btc_amount = floor(btc_amount / step_size) * step_size
            btc_amount = round(btc_amount, 6)  # Redondear a 6 decimales
            print(f"Cantidad ajustada de BTC a comprar: {btc_amount}")

            # Verificar si la cantidad cumple con el mínimo
            if btc_amount < min_qty:
                print(f"Error: La cantidad ajustada de BTC ({btc_amount}) es menor al mínimo permitido ({min_qty}).")
                return

            # Realizar la orden de compra (mercado)
            order = client.order_market_buy(
                symbol=symbol,
                quantity=btc_amount
            )
            print(f"Orden de compra ejecutada: {order}")

        except Exception as e:
            print(f"Error al comprar BTC: {e}")
            # [NUEVO] Si hubo error, NO cambiamos variables ni estados (evita fallo por compra no ejecutada)
            return

        print(f"Orden de compra ejecutada (Spot principal): {order}")

        # [NUEVO] ---------------------------------------------------------
        # Enviamos también la orden a la billetera líder (Copy Trading).
        if symbol.endswith("USDT"):
            try:
                order_lead = client_lead.order_market_buy(
                    symbol=symbol,
                    quantity=btc_amount
                )
                print(f"Orden de compra ejecutada (Billetera líder): {order_lead}")
            except Exception as e_lead:
                print(f"[Billetera líder] Error al comprar BTC en copy trading: {e_lead}")
        else:
            print("[Billetera líder] Par no soportado (solo USDT). Se omite la orden.")

    except Exception as e:
        print(f"Error al comprar BTC: {e}")

def vender_btc():
    """
    Vende todo el saldo disponible de BTC y lo convierte a USDT.
    """
    try:
        global ultimo_precio_venta
        global tiempo_ultima_venta
        global precio_stop_loss

        # --- CÓDIGO ORIGINAL (NO SE MODIFICA) ---
        btc_balance = float(client.get_asset_balance(asset="BTC")["free"])
        print(f"Saldo disponible en BTC: {btc_balance}")

        symbol = "BTCUSDT"
        exchange_info = client.get_symbol_info(symbol)
        for filtro in exchange_info["filters"]:
            if filtro["filterType"] == "LOT_SIZE":
                min_qty = float(filtro["minQty"])
                step_size = float(filtro["stepSize"])
                break

        btc_amount = floor(btc_balance / step_size) * step_size
        btc_amount = round(btc_amount, 6)

        """
            Vende todo el saldo disponible de BTC y lo convierte a USDT en la cuenta de líder de trading.
            """
        try:
            # Obtener saldo disponible en BTC
            btc_balance = float(client.get_asset_balance(asset="BTC")["free"])
            print(f"Saldo disponible en BTC: {btc_balance}")

            if btc_balance <= 0:
                print("Saldo insuficiente en BTC para realizar la venta.")
                return

            # Obtener LOT_SIZE dinámicamente
            symbol = "BTCUSDT"
            exchange_info = client.get_symbol_info(symbol)
            for filtro in exchange_info["filters"]:
                if filtro["filterType"] == "LOT_SIZE":
                    min_qty = float(filtro["minQty"])
                    step_size = float(filtro["stepSize"])
                    break

            # Ajustar la cantidad de BTC a vender al múltiplo permitido
            btc_amount = floor(btc_balance / step_size) * step_size
            btc_amount = round(btc_amount, 6)  # Redondear a 6 decimales
            print(f"Cantidad ajustada de BTC a vender: {btc_amount}")

            # Verificar si la cantidad cumple con el mínimo permitido
            if btc_amount < min_qty:
                print(f"Error: La cantidad ajustada de BTC ({btc_amount}) es menor al mínimo permitido ({min_qty}).")
                return

            # Realizar la orden de venta (mercado)
            order = client.order_market_sell(
                symbol=symbol,
                quantity=btc_amount
            )
            print(f"Orden de venta ejecutada: {order}")

        except Exception as e:
            print(f"Error al vender BTC: {e}")
            return

        # [NUEVO] Guardamos último precio y momento de venta (existe en tu código).
        symbol = "BTCUSDT"
        ticker_temp = client.get_symbol_ticker(symbol=symbol)
        ultimo_precio_venta = float(ticker_temp["price"])
        tiempo_ultima_venta = time.time()
        # [NUEVO] Resetear precio stop-loss después de vender
        precio_stop_loss = None

        # [NUEVO] -------------------------------------------------
        # Intentar también la venta en la billetera líder (Copy).
        if symbol.endswith("USDT"):
            try:
                btc_balance_lead = float(client_lead.get_asset_balance(asset="BTC")["free"])
                print(f"[Billetera líder] Saldo disponible en BTC: {btc_balance_lead}")

                btc_amount_lead = floor(btc_balance_lead / step_size) * step_size
                btc_amount_lead = round(btc_amount_lead, 6)
                print(f"[Billetera líder] BTC a vender: {btc_amount_lead}")

                if btc_amount_lead < min_qty:
                    print(f"[Billetera líder] La cantidad ({btc_amount_lead}) es menor al mínimo permitido ({min_qty}). No se vende.")
                else:
                    order_lead = client_lead.order_market_sell(
                        symbol=symbol,
                        quantity=btc_amount_lead
                    )
                    print(f"[Billetera líder] Orden de venta ejecutada (Copy Trading): {order_lead}")

            except Exception as e_lead_sell:
                print(f"[Billetera líder] Error al vender BTC en copy trading: {e_lead_sell}")
        else:
            print("[Billetera líder] Par no soportado (solo USDT). Se omite la orden.")

    except Exception as e:
        print(f"Error al vender BTC: {e}")

def obtener_precio_bitcoin():
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker('BTC/USDT')
        return ticker['last']
    except Exception as e:
        # Para no saturar la consola, comentamos el print detallado
        # print("Error al obtener precio de Bitcoin:", e)
        return None

# --------------------------------------------------------------------------------
# Función para obtener indicadores (corto plazo) + SuperTrend con nombres dinámicos
# --------------------------------------------------------------------------------
def obtener_indicadores(exchange, symbol='BTC/USDT', timeframe='1m', limit=60):
    """
    Devuelve un DataFrame con RSI, MACD, ADX y la señal de SuperTrend (columna 'supertrend_dir').
    Detecta automáticamente el nombre que generó pandas_ta para 'SUPERTd_...'
    """
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        if len(df) < 14:
            return None

        # Indicadores estándar
        df['rsi'] = ta.rsi(df['close'], length=5).fillna(method='bfill')
        macd = ta.macd(df['close'], fast=5, slow=13, signal=4)
        df['macd'] = macd['MACD_5_13_4'].fillna(method='bfill')
        df['macd_signal'] = macd['MACDs_5_13_4'].fillna(method='bfill')
        df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=5)['ADX_5'].fillna(method='bfill')

        # SuperTrend
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
        direction_cols = [col for col in st.columns if col.startswith('SUPERTd')]
        if len(direction_cols) == 0:
            # print("  [DEBUG] No se encontró columna SUPERTd_ en SuperTrend.")
            return None

        direction_col = direction_cols[0]
        df['supertrend_dir'] = st[direction_col].fillna(method='bfill')

        return df
    except Exception:
        return None

# ... aquí continúan todas tus funciones auxiliares: verificar_tendencia_largo_plazo, supertrend_bajista, evitar_caida, verificar_tendencia_mediano_plazo, etc. ... 
# NO SE OMITEN, simplemente cópialas aquí tal como ya las tienes arriba

# [NUEVO] Filtro forecast usando polyfit
def forecast_pendiente_alcista(exchange, symbol='BTC/USDT', timeframe='1m', minutos=180):
    """
    Filtro: Solo comprar si la pendiente lineal de los últimos 'minutos' es >= 0 (o según quieras).
    """
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=minutos)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        closes = df['close'].values
        x = np.arange(len(closes))
        coef = np.polyfit(x, closes, 1)
        pendiente = coef[0]
        print(f"[FORECAST] Pendiente (np.polyfit) últimas {minutos} min: {pendiente:.6f}")
        return pendiente > 0
    except Exception as e:
        print(f"Error forecast con polyfit: {e}")
        return False

# ... aquí continúa todo tu bloque de validaciones y filtros ...
# (cópialas completas, igual que estaban en tu mensaje anterior)

# --------------------------------------------------------------------------------
# Lógica principal (Código original, SIN CAMBIOS, salvo integración)
# --------------------------------------------------------------------------------
def main():
    exchange = ccxt.binance()

    while True:
        precioguardado = obtener_precio_bitcoin()
        if precioguardado is None:
            time.sleep(5)
            continue
        break

    en_dolares = True
    cooldown_segundos = 1
    ultima_operacion = time.time() - cooldown_segundos

    tiempo_espera_usd = 50  # 30 min
    t_inicio = time.time()
    precio_inicial_usd = precioguardado
    compra_realizada = False

    global precio_stop_loss

    while True:
        try:
            precio_actual = obtener_precio_bitcoin()
            if precio_actual is None:
                time.sleep(0.2)
                continue

            variacion = (precio_actual - precioguardado) / precioguardado * 100
            tiempo_desde_ultima_operacion = time.time() - ultima_operacion
            tiempo_transcurrido = time.time() - t_inicio
            tiempo_en_usd = tiempo_transcurrido

            df = obtener_indicadores(exchange)
            if df is None:
                time.sleep(5)
                continue

            # Filtros ya existentes
            tendencia_bajista_largo_plazo = verificar_tendencia_largo_plazo(exchange)
            supertrend_es_bajista = supertrend_bajista(df)
            indicadores_desfavorables = evitar_caida(df)
            tendencia_mediano_plazo_ok = verificar_tendencia_mediano_plazo(exchange)

            # [NUEVO] STOP-LOSS: Si estamos en BTC, revisa si hay que ejecutar venta forzada
            if not en_dolares and stop_loss_activado and precio_stop_loss is not None:
                if precio_actual <= precio_stop_loss:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now_str}] *** STOP-LOSS activado. VENTA FORZADA a ${precio_actual:.2f} ***")
                    vender_btc()
                    precioguardado = precio_actual
                    en_dolares = True
                    ultima_operacion = time.time()
                    compra_realizada = False
                    precio_stop_loss = None
                    time.sleep(5)
                    continue

            if en_dolares:
                # Condición de compra (original):
                cond_1 = (precio_actual <= precio_inicial_usd * 0.995 -0.1) or (tiempo_en_usd >= 1800 and not indicadores_desfavorables)
                cond_2 = not tendencia_bajista_largo_plazo
                cond_3 = not supertrend_es_bajista
                cond_4 = tendencia_mediano_plazo_ok

                # [NUEVO] Filtro forecast
                forecast_ok = forecast_pendiente_alcista(exchange)

                if cond_1 and cond_2 and cond_3 and cond_4 and forecast_ok:
                    if validacion_adicional(exchange):
                        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        print(f"[{now_str}] ** COMPRA de BTC a ${precio_actual:.2f} **")
                        comprar_btc()

                        precioguardado = precio_actual
                        en_dolares = False
                        ultima_operacion = time.time()
                        compra_realizada = True
                    else:
                        print("Validación adicional desaconseja la compra. Se omite la operación.")
                elif not forecast_ok:
                    print("Forecast de tendencia lineal desaconseja la compra. Se omite la operación.")

            else:
                # Lógica de venta (original)
                if variacion >= 0.5:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now_str}] ** El precio ha subido 0.5%. VENTA de BTC a ${precio_actual:.2f} **")
                    vender_btc()

                    precioguardado = precio_actual
                    en_dolares = True
                    ultima_operacion = time.time()
                    compra_realizada = False
                    precio_stop_loss = None

                elif not indicadores_desfavorables and precio_actual > precioguardado * 1.0079:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now_str}] ** Condiciones desfavorables. VENTA anticipada de BTC a ${precio_actual:.2f} **")
                    vender_btc()

                    precioguardado = precio_actual
                    en_dolares = True
                    ultima_operacion = time.time()
                    compra_realizada = False
                    precio_stop_loss = None

            time.sleep(5)

        except Exception as e:
            # print("Error en bucle principal:", e)
            time.sleep(0.2)

if __name__ == "__main__":
    main()
