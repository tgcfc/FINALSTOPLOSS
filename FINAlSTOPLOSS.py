 import sys
import random
import string
import time
import ccxt
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from binance.client import Client
from math import floor

# [NUEVO] Variables globales para recompra y stop-loss
ultimo_precio_venta = None
tiempo_ultima_venta = 0
ultimo_precio_compra = None
stop_loss_pct = 0.995  # 0.5% stop-loss

# [NUEVO] Para forecast regresión lineal
from sklearn.linear_model import LinearRegression
import numpy as np

def ajustar_cantidad(cantidad, step_size):
    return floor(cantidad / step_size) * step_size

# API KEYS
API_KEY = "wNmoR7nXAk2rNR5KjqeeKPfF7sEWeQFCgzjFqSLvMYEsqI3T4LEw4R0Q9TtjhBTV"
API_SECRET = "EQG2eGIdB4ibN0ua4vlTTqSqlGIvcxK2wsoif5k6Ch0DyLFgnBJ3z6Vv6dvMSZnC"
client = Client(API_KEY, API_SECRET)

COPY_API_KEY = "Xb4SIWG5FzQR5fAzTcRigalhughRm5u3uovVCWSidOIcMzpV78KXXO7hezrY53Hq"
COPY_API_SECRET = "yBbmeWOjc70SbGwNYcNuspnUw5gMfe7uIKmd9eO1N5EvIejhLz0x4W9ezci0RXqT"
client_lead = Client(COPY_API_KEY, COPY_API_SECRET)
client = Client(COPY_API_KEY, COPY_API_SECRET)  # usar las del líder

# ----------- INDICADORES Y FUNCIONES ORIGINALES -----------------

def obtener_precio_bitcoin():
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker('BTC/USDT')
        return ticker['last']
    except Exception as e:
        return None

def forecast_pendiente_alcista(exchange, symbol='BTC/USDT', timeframe='1m', minutos=180):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=minutos)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        closes = df['close'].values
        x = np.arange(len(closes)).reshape(-1, 1)
        y = closes.reshape(-1, 1)
        model = LinearRegression().fit(x, y)
        pendiente = model.coef_[0][0]
        print(f"Pendiente forecast últimas 3h: {pendiente:.6f}")
        return pendiente > 0
    except Exception as e:
        print(f"Error en forecast/regresión: {e}")
        return False

def obtener_indicadores(exchange, symbol='BTC/USDT', timeframe='1m', limit=60):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        if len(df) < 14:
            return None
        df['rsi'] = ta.rsi(df['close'], length=5).fillna(method='bfill')
        macd = ta.macd(df['close'], fast=5, slow=13, signal=4)
        df['macd'] = macd['MACD_5_13_4'].fillna(method='bfill')
        df['macd_signal'] = macd['MACDs_5_13_4'].fillna(method='bfill')
        df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=5)['ADX_5'].fillna(method='bfill')
        st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
        direction_cols = [col for col in st.columns if col.startswith('SUPERTd')]
        if len(direction_cols) == 0:
            return None
        direction_col = direction_cols[0]
        df['supertrend_dir'] = st[direction_col].fillna(method='bfill')
        return df
    except Exception:
        return None

def verificar_tendencia_largo_plazo(exchange, symbol='BTC/USDT', timeframe='1h', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        if len(df) < 50:
            return False
        df['ma_50'] = ta.sma(df['close'], length=50).fillna(method='bfill')
        df['rsi_14'] = ta.rsi(df['close'], length=14).fillna(method='bfill')
        precio_actual = df['close'].iloc[-1]
        ma_50_actual = df['ma_50'].iloc[-1]
        rsi_14_actual = df['rsi_14'].iloc[-1]
        if precio_actual < ma_50_actual and rsi_14_actual < 30:
            return True
        return False
    except Exception:
        return False

def supertrend_bajista(df):
    try:
        if 'supertrend_dir' not in df.columns:
            return False
        ultima_senal = df['supertrend_dir'].iloc[-1]
        return (ultima_senal == -1)
    except Exception:
        return False

def evitar_caida(df):
    if df is None:
        return True
    try:
        rsi_actual = df['rsi'].iloc[-1]
        macd_actual = df['macd'].iloc[-1]
        macd_signal_actual = df['macd_signal'].iloc[-1]
        adx_actual = df['adx'].iloc[-1]
        if pd.isna(rsi_actual) or pd.isna(macd_actual) or pd.isna(macd_signal_actual) or pd.isna(adx_actual):
            return True
        if not (30 < rsi_actual < 70):
            return True
        if macd_actual <= macd_signal_actual:
            return True
        if adx_actual < 25:
            return True
        return False
    except Exception:
        return True

def verificar_tendencia_mediano_plazo(exchange, symbol='BTC/USDT', timeframe='15m', limit=60):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        if len(df) < 14:
            return False
        df['rsi'] = ta.rsi(df['close'], length=14).fillna(method='bfill')
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        df['macd'] = macd['MACD_12_26_9'].fillna(method='bfill')
        df['macd_signal'] = macd['MACDs_12_26_9'].fillna(method='bfill')
        rsi_15m = df['rsi'].iloc[-1]
        macd_15m = df['macd'].iloc[-1]
        macd_signal_15m = df['macd_signal'].iloc[-1]
        if rsi_15m > 50 and macd_15m > macd_signal_15m:
            return True
        return False
    except Exception:
        return False

# ----- FILTROS DE NOTICIAS, HORARIO, ETC -----
CRYPTOPANIC_API_TOKEN = "37b99aaaf91a61655f4d64f82d16aeccfe7223b2"
CRYPTOPANIC_ENDPOINT = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_TOKEN}&filter=negative,important"
FEAR_GREED_ENDPOINT = "https://api.alternative.me/fng/"

def check_noticias_negativas() -> bool:
    try:
        response = requests.get(CRYPTOPANIC_ENDPOINT, timeout=10)
        if response.status_code == 200:
            data = response.json()
            posts = data.get("results", [])
            ahora = datetime.utcnow()
            recientes = [
                post for post in posts
                if "published_at" in post and
                (ahora - datetime.fromisoformat(post["published_at"][:-1])).total_seconds() <= 21600
            ]
            if len(recientes) >= 40:
                print(f"Se encontraron {len(recientes)} noticias negativas recientes en CryptoPanic.")
                return True
            return False
        else:
            print(f"Error CryptoPanic: status {response.status_code}")
            return False
    except Exception as e:
        print(f"Error al consultar CryptoPanic: {e}")
        return False

def check_horarios_preferidos() -> bool:
    ahora = datetime.now().hour
    if 23 <= ahora or ahora < 1:
        return False
    return True

def check_fear_and_greed() -> bool:
    try:
        r = requests.get(FEAR_GREED_ENDPOINT, timeout=10)
        if r.status_code == 200:
            fng_data = r.json()
            fng_list = fng_data.get("data", [])
            if not fng_list:
                print("Sin datos Fear & Greed => Continuamos sin bloquear.")
                return True
            latest = fng_list[0]
            fng_value_str = latest.get("value", "50")
            fng_value = int(fng_value_str)
            if fng_value < 20:
                print(f"Fear & Greed Index muy bajo ({fng_value}) => Pánico extremo.")
                return False
            return True
        else:
            print(f"Error Fear & Greed Index: status {r.status_code}")
            return True
    except Exception as e:
        print(f"Error al consultar Fear & Greed: {e}")
        return True

def check_atr_alto(exchange, symbol='BTC/USDT') -> bool:
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        if len(df) < 14:
            return False
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        precio_actual = df['close'].iloc[-1]
        atr_actual = df['atr'].iloc[-1]
        umbral_atr = precio_actual * 0.005
        if atr_actual > umbral_atr:
            print(f"ATR = {atr_actual:.2f}, supera el umbral dinámico de {umbral_atr:.2f}")
            return True
        return False
    except:
        return False

def check_volumen_bajo(exchange, symbol='BTC/USDT') -> bool:
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=10)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        avg_volume = df['volume'].mean()
        if avg_volume < 50:
            print("Volumen de negociación muy bajo => Bloquear compra.")
            return True
        return False
    except:
        return False

def check_heikin_ashi(exchange, symbol='BTC/USDT', timeframe='15m', limit=30) -> bool:
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        ha_df = df.copy()
        ha_df['HA_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        ha_df['HA_open'] = 0.0
        for i in range(len(ha_df)):
            if i == 0:
                ha_df.at[i, 'HA_open'] = (df['open'].iloc[i] + df['close'].iloc[i]) / 2
            else:
                ha_df.at[i, 'HA_open'] = (ha_df.at[i-1, 'HA_open'] + ha_df.at[i-1, 'HA_close']) / 2
        ha_df['HA_high'] = ha_df[['HA_open','HA_close','high']].max(axis=1)
        ha_df['HA_low']  = ha_df[['HA_open','HA_close','low']].min(axis=1)
        ultimas_velas = ha_df.tail(3)
        todas_alcistas = all(ultimas_velas['HA_close'] > ultimas_velas['HA_open'])
        if not todas_alcistas:
            print("Heikin Ashi: Últimas velas no son completamente alcistas.")
        return todas_alcistas
    except:
        return True

def check_rsi_multiple_timeframes(exchange, symbol='BTC/USDT') -> bool:
    timeframes = ['5m', '15m', '1h']
    for tf in timeframes:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=30)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['rsi'] = ta.rsi(df['close'], length=14).fillna(method='bfill')
            rsi_ultima = df['rsi'].iloc[-1]
            if rsi_ultima < 40:
                print(f"RSI de {tf} = {rsi_ultima:.2f}, alarmista => Bloquear compra.")
                return False
        except Exception as e:
            print(f"Error al calcular RSI en {tf}: {e}")
            return False
    return True

def check_binance_24h_ticker() -> bool:
    url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            cambio_24h = float(data["priceChangePercent"])
            print(f"Variación 24h en Binance: {cambio_24h:.2f}%")
            if abs(cambio_24h) > 10:
                print("Cambio 24h excede ±10%, demasiada volatilidad => Bloquear compra.")
                return False
            return True
        else:
            print(f"Error consultando 24h ticker: {r.status_code}")
            return True
    except Exception as e:
        print(f"Excepción en check_binance_24h_ticker: {e}")
        return True

def validacion_adicional(exchange) -> bool:
    if check_noticias_negativas():
        print("Alertas negativas en noticias => Bloquear compra.")
        return False
    if not check_horarios_preferidos():
        print("Estamos en horario de alta volatilidad => Bloquear compra.")
        return False
    if not check_fear_and_greed():
        print("Índice de Miedo & Avaricia muy bajo => Bloquear compra.")
        return False
    if check_atr_alto(exchange):
        print("Volatilidad (ATR) demasiado alta => Bloquear compra.")
        return False
    if check_volumen_bajo(exchange):
        return False
    if not check_heikin_ashi(exchange):
        print("Velas Heikin Ashi no confirman tendencia alcista => Bloquear compra.")
        return False
    if not check_rsi_multiple_timeframes(exchange):
        print("RSI en múltiples marcos detecta condiciones muy adversas => Bloquear compra.")
        return False
    if not check_binance_24h_ticker():
        print("Variación 24h en Binance demasiado alta => Bloquear compra.")
        return False
    return True

# ------------- ORDENES DE COMPRA/VENTA -------------

def comprar_btc(precio_compra=None):
    try:
        global ultimo_precio_venta
        global tiempo_ultima_venta
        global ultimo_precio_compra

        if ultimo_precio_venta is not None:
            tiempo_desde_venta = time.time() - tiempo_ultima_venta
            if tiempo_desde_venta < 1200:
                symbol = "BTCUSDT"
                ticker_temp = client.get_symbol_ticker(symbol=symbol)
                btc_price_temp = float(ticker_temp["price"])
                if btc_price_temp > ultimo_precio_venta:
                    print("Restricción de recompra: han pasado menos de 20 min y el precio está por encima de la última venta. Se bloquea la compra.")
                    return False

        usdt_balance = float(client.get_asset_balance(asset="USDT")["free"])
        try:
            usdt_balance = float(client.get_asset_balance(asset="USDT")["free"])
            print(f"Saldo disponible en USDT: {usdt_balance}")
            if usdt_balance <= 0:
                print("Saldo insuficiente en USDT para realizar la compra.")
                return False
            symbol = "BTCUSDT"
            ticker = client.get_symbol_ticker(symbol=symbol)
            btc_price = float(ticker["price"])
            print(f"Precio actual de BTC/USDT: {btc_price}")
            exchange_info = client.get_symbol_info(symbol)
            for filtro in exchange_info["filters"]:
                if filtro["filterType"] == "LOT_SIZE":
                    min_qty = float(filtro["minQty"])
                    step_size = float(filtro["stepSize"])
                    break
            btc_amount = usdt_balance / btc_price
            btc_amount = floor(btc_amount / step_size) * step_size
            btc_amount = round(btc_amount, 6)
            print(f"Cantidad ajustada de BTC a comprar: {btc_amount}")
            if btc_amount < min_qty:
                print(f"Error: La cantidad ajustada de BTC ({btc_amount}) es menor al mínimo permitido ({min_qty}).")
                return False
            order = client.order_market_buy(
                symbol=symbol,
                quantity=btc_amount
            )
            print(f"Orden de compra ejecutada: {order}")
        except Exception as e:
            print(f"Error al comprar BTC: {e}")
            return False

        print(f"Orden de compra ejecutada (Spot principal): {order}")

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

        if precio_compra is not None:
            ultimo_precio_compra = precio_compra
        else:
            ultimo_precio_compra = btc_price

        return True

    except Exception as e:
        print(f"Error al comprar BTC: {e}")
        return False

def vender_btc():
    try:
        global ultimo_precio_venta
        global tiempo_ultima_venta

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
        try:
            btc_balance = float(client.get_asset_balance(asset="BTC")["free"])
            print(f"Saldo disponible en BTC: {btc_balance}")

            if btc_balance <= 0:
                print("Saldo insuficiente en BTC para realizar la venta.")
                return

            symbol = "BTCUSDT"
            exchange_info = client.get_symbol_info(symbol)
            for filtro in exchange_info["filters"]:
                if filtro["filterType"] == "LOT_SIZE":
                    min_qty = float(filtro["minQty"])
                    step_size = float(filtro["stepSize"])
                    break
            btc_amount = floor(btc_balance / step_size) * step_size
            btc_amount = round(btc_amount, 6)
            print(f"Cantidad ajustada de BTC a vender: {btc_amount}")
            if btc_amount < min_qty:
                print(f"Error: La cantidad ajustada de BTC ({btc_amount}) es menor al mínimo permitido ({min_qty}).")
                return
            order = client.order_market_sell(
                symbol=symbol,
                quantity=btc_amount
            )
            print(f"Orden de venta ejecutada: {order}")
        except Exception as e:
            print(f"Error al vender BTC: {e}")

        symbol = "BTCUSDT"
        ticker_temp = client.get_symbol_ticker(symbol=symbol)
        ultimo_precio_venta = float(ticker_temp["price"])
        tiempo_ultima_venta = time.time()

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

# ----------- LOOP PRINCIPAL -----------

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

    global ultimo_precio_compra, stop_loss_pct

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

            tendencia_bajista_largo_plazo = verificar_tendencia_largo_plazo(exchange)
            supertrend_es_bajista = supertrend_bajista(df)
            indicadores_desfavorables = evitar_caida(df)
            tendencia_mediano_plazo_ok = verificar_tendencia_mediano_plazo(exchange)

            # [STOP LOSS]
            if not en_dolares and ultimo_precio_compra is not None:
                if precio_actual <= ultimo_precio_compra * stop_loss_pct:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now_str}] ** STOP-LOSS activado. VENTA de BTC a ${precio_actual:.2f} **")
                    vender_btc()
                    precioguardado = precio_actual
                    en_dolares = True
                    ultima_operacion = time.time()
                    compra_realizada = False
                    ultimo_precio_compra = None
                    time.sleep(5)
                    continue

            if en_dolares:
                cond_1 = (precio_actual <= precio_inicial_usd * 0.995 -0.1) or (tiempo_en_usd >= 1800 and not indicadores_desfavorables)
                cond_2 = not tendencia_bajista_largo_plazo
                cond_3 = not supertrend_es_bajista
                cond_4 = tendencia_mediano_plazo_ok

                if cond_1 and cond_2 and cond_3 and cond_4:
                    if validacion_adicional(exchange):
                        if not forecast_pendiente_alcista(exchange):
                            print("Forecast de regresión indica tendencia bajista. Se omite la compra.")
                        else:
                            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            print(f"[{now_str}] ** COMPRA de BTC a ${precio_actual:.2f} **")
                            ejecutada = comprar_btc(precio_compra=precio_actual)
                            if ejecutada:
                                precioguardado = precio_actual
                                en_dolares = False
                                ultima_operacion = time.time()
                                compra_realizada = True
                            else:
                                print("Fallo en la ejecución de la compra. Seguimos en USDT.")
                    else:
                        print("Validación adicional desaconseja la compra. Se omite la operación.")

            else:
                if variacion >= 0.5:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now_str}] ** El precio ha subido 0.5%. VENTA de BTC a ${precio_actual:.2f} **")
                    vender_btc()
                    precioguardado = precio_actual
                    en_dolares = True
                    ultima_operacion = time.time()
                    compra_realizada = False
                    ultimo_precio_compra = None

                elif not indicadores_desfavorables and precio_actual > precioguardado * 1.0079:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"[{now_str}] ** Condiciones desfavorables. VENTA anticipada de BTC a ${precio_actual:.2f} **")
                    vender_btc()
                    precioguardado = precio_actual
                    en_dolares = True
                    ultima_operacion = time.time()
                    compra_realizada = False
                    ultimo_precio_compra = None

            time.sleep(5)

        except Exception as e:
            time.sleep(0.2)

if __name__ == "__main__":
    main()
