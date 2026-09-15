import asyncio
import time
import ccxt.async_support as ccxt
import pandas as pd
import ta
import streamlit as st

# ==========================================
# ⚙️ ОСНОВНІ НАЛАШТУВАННЯ СКАНЕРА (BINANCE)
# ==========================================
TIMEFRAME = '4h'
RSI_THRESHOLD = 75         # Поріг RSI для перегріву
VOL_MULTIPLIER = 2.0       # Спайк об'єму (в N разів вище середнього за 20 свічок)
MIN_UPPER_SHADOW = 0.35    # Частка верхньої тіні (35% від всієї свічки)

# ==========================================
# 🛠 ФУНКЦІЇ АНАЛІЗУ РИНКУ
# ==========================================
def calculate_vwap(df):
    """Розрахунок спрощеного VWAP за останні свічки"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).sum() / df['volume'].sum()

async def fetch_pair_data(exchange, symbol, semaphore):
    """Завантаження свічок з Binance з обробкою лімітів"""
    async with semaphore:
        for attempt in range(3):
            try:
                await asyncio.sleep(0.05)  # Затримка між запитами
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=60)
                if len(ohlcv) < 50:
                    return None

                df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                
                df['RSI'] = ta.momentum.rsi(df['close'], window=14)
                df['SMA_VOL'] = ta.trend.sma_indicator(df['volume'], window=20)
                vwap_val = calculate_vwap(df.tail(20))
                
                last = df.iloc[-1]
                candle_range = last['high'] - last['low']
                
                if candle_range == 0 or pd.isna(last['RSI']):
                    return None
                    
                upper_shadow = last['high'] - max(last['open'], last['close'])
                shadow_ratio = upper_shadow / candle_range
                
                is_rsi_high = last['RSI'] > RSI_THRESHOLD
                is_vol_high = last['volume'] > (last['SMA_VOL'] * VOL_MULTIPLIER)
                
                if is_rsi_high or is_vol_high:
                    if is_rsi_high and is_vol_high and shadow_ratio >= MIN_UPPER_SHADOW:
                        verdict = "🔴 SHORT-СЕТАП"
                    elif is_rsi_high and is_vol_high:
                        verdict = "⚠️ ФОРМУЄТЬСЯ"
                    else:
                        verdict = "👀 НАБЛЮДАТИ"
                        
                    vol_ratio = last['volume'] / last['SMA_VOL'] if last['SMA_VOL'] > 0 else 0
                    vwap_diff = ((last['close'] - vwap_val) / vwap_val) * 100
                    
                    clean_ticker = symbol.split('/')[0].split(':')[0]
                    
                    return {
                        "Токен": clean_ticker,
                        "Ціна ($)": round(last['close'], 5),
                        "RSI (4H)": round(last['RSI'], 1),
                        "Об'єм (х)": round(vol_ratio, 1),
                        "Тінь (%)": round(shadow_ratio * 100, 1),
                        "Відхилення VWAP (%)": f"{vwap_diff:+.1f}%",
                        "Вердикт": verdict
                    }
                break
            except ccxt.RateLimitExceeded:
                await asyncio.sleep(1.5 * (attempt + 1))
            except Exception:
                return None
        return None

async def scan_binance_market():
    """Сканування всіх USDT-ф'ючерсів на Binance"""
    exchange = ccxt.binanceusdm({'enableRateLimit': True})
    semaphore = asyncio.Semaphore(10)  # Binance легко витримує 10 паралельних запитів
    results = []
    
    try:
        markets = await exchange.load_markets()
        usdt_pairs = [
            symbol for symbol, market in markets.items()
            if market.get('linear') and market.get('settle') == 'USDT' and market.get('active')
        ]
        
        tasks = [fetch_pair_data(exchange, symbol, semaphore) for symbol in usdt_pairs]
        data_list = await asyncio.gather(*tasks)
        
        results = [item for item in data_list if item is not None]
    finally:
        await exchange.close()
        
    return results

# ==========================================
# 🖥 ІНТЕРФЕЙС STREAMLIT
# ==========================================
st.set_page_config(page_title="Binance Overheat Scanner", page_icon="🔥", layout="wide")

st.title("🔥 Сканер Перегрітих Криптоактивів (Binance Futures 4H)")
st.caption("Автоматичний аналіз RSI, сплесків об'єму, відхилення від VWAP та свічних паттернів.")

if st.button("🔄 Оновити дані зараз") or 'results' not in st.session_state:
    with st.spinner("Сканування ринку Binance Futures... Зачекайте близько 5-10 секунд"):
        st.session_state['results'] = asyncio.run(scan_binance_market())
        st.session_state['last_update'] = time.strftime("%H:%M:%S")

results = st.session_state.get('results', [])
last_update = st.session_state.get('last_update', 'Ніколи')

st.write(f"**Останнє оновлення:** `{last_update}` | **Знайдено перегрітих пар:** `{len(results)}`")

if results:
    df_results = pd.DataFrame(results)
    
    filter_verdict = st.multiselect(
        "Фільтр вердиктів:", 
        options=["🔴 SHORT-СЕТАП", "⚠️ ФОРМУЄТЬСЯ", "👀 НАБЛЮДАТИ"],
        default=["🔴 SHORT-СЕТАП", "⚠️ ФОРМУЄТЬСЯ"]
    )
    
    filtered_df = df_results[df_results["Вердикт"].isin(filter_verdict)]
    
    def highlight_verdict(val):
        if val == "🔴 SHORT-СЕТАП":
            return 'background-color: #ff4d4d; color: white; font-weight: bold;'
        elif val == "⚠️ ФОРМУЄТЬСЯ":
            return 'background-color: #ffa64d; color: black;'
        return ''

    styled_df = filtered_df.style.map(highlight_verdict, subset=["Вердикт"])
    
    st.dataframe(styled_df, use_container_width=True, height=450)
else:
    st.info("На даний момент перегрітих пар на ринку Binance не виявлено.")
