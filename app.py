import asyncio
import time
import ccxt.async_support as ccxt
import pandas as pd
import ta
import streamlit as st

# ==========================================
# ⚙️ ОСНОВНІ НАЛАШТУВАННЯ СКАНЕРА
# ==========================================
TIMEFRAME = '4h'
RSI_THRESHOLD = 75         # Поріг RSI для перегріву
VOL_MULTIPLIER = 2.0       # Спайк об'єму (в N разів вище середнього за 20 свічок)
MIN_UPPER_SHADOW = 0.35    # Частка верхньої тіні (35% від всієї свічки)
MIN_24H_VOL_USD = 5000000  # Фільтр за об'ємом за 24г ($5M+)

# ==========================================
# 🛠 ФУНКЦІЇ АНАЛІЗУ РИНКУ
# ==========================================
def calculate_vwap(df):
    """Розрахунок спрощеного VWAP за останні свічки"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).sum() / df['volume'].sum()

async def fetch_pair_data(exchange, symbol):
    """Завантаження свічок та обчислення метрик перегріву"""
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=60)
        if len(ohlcv) < 50:
            return None

        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        # Обчислення індикаторів через бібліотеку ta
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
            
            return {
                "Токен": symbol.split(':')[0].replace('/USDT', ''),
                "Ціна ($)": round(last['close'], 5),
                "RSI (4H)": round(last['RSI'], 1),
                "Об'єм (х)": round(vol_ratio, 1),
                "Тінь (%)": round(shadow_ratio * 100, 1),
                "Відхилення VWAP (%)": f"{vwap_diff:+.1f}%",
                "Вердикт": verdict
            }
    except Exception:
        return None
    return None

async def scan_bybit_market():
    """Сканування всіх USDT-пар на Bybit"""
    exchange = ccxt.bybit({'enableRateLimit': True})
    results = []
    
    try:
        tickers = await exchange.fetch_tickers()
        usdt_pairs = [
            symbol for symbol, data in tickers.items()
            if symbol.endswith(':USDT') and (data.get('quoteVolume') or 0) > MIN_24H_VOL_USD
        ]
        
        tasks = [fetch_pair_data(exchange, symbol) for symbol in usdt_pairs]
        data_list = await asyncio.gather(*tasks)
        
        results = [item for item in data_list if item is not None]
    finally:
        await exchange.close()
        
    return results

# ==========================================
# 🖥 ІНТЕРФЕЙС STREAMLIT
# ==========================================
st.set_page_config(page_title="Crypto Overheat Scanner", page_icon="🔥", layout="wide")

st.title("🔥 Сканер Перегрітих Криптоактивів (Bybit 4H)")
st.caption("Автоматичний аналіз RSI, сплесків об'єму, відхилення від VWAP та свічних паттернів.")

if st.button("🔄 Оновити дані зараз") or 'results' not in st.session_state:
    with st.spinner("Сканування ринку Bybit..."):
        st.session_state['results'] = asyncio.run(scan_bybit_market())
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
    st.info("На даний момент перегрітих пар на ринку не виявлено або ринок перебуває у флеті.")
