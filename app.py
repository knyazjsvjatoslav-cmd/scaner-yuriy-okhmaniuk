import time
import ccxt
import pandas as pd
import ta
import streamlit as st

# ==========================================
# ⚙️ НАЛАШТУВАННЯ СКАНЕРА
# ==========================================
TIMEFRAME = '4h'

# Пороги Перегріву (SHORT)
RSI_OVERBOUGHT = 75
MIN_UPPER_SHADOW = 0.35

# Пороги Переохолодження (LONG)
RSI_OVERSOLD = 30
MIN_LOWER_SHADOW = 0.35

# Загальні
VOL_MULTIPLIER = 2.0

def calculate_vwap(df):
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).sum() / df['volume'].sum()

def scan_mexc_market():
    exchange = ccxt.mexc({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    results = []
    
    try:
        markets = exchange.load_markets()
        usdt_pairs = [
            symbol for symbol, market in markets.items()
            if market.get('swap') and market.get('settle') == 'USDT' and market.get('active')
        ]
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        pairs_to_scan = usdt_pairs[:100]  # Можна збільшити кількість пар
        total_pairs = len(pairs_to_scan)
        
        for idx, symbol in enumerate(pairs_to_scan):
            status_text.text(f"Аналіз пара {idx+1}/{total_pairs}: {symbol.split(':')[0]}")
            progress_bar.progress((idx + 1) / total_pairs)
            
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=60)
                if len(ohlcv) < 50:
                    continue

                df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                
                df['RSI'] = ta.momentum.rsi(df['close'], window=14)
                df['SMA_VOL'] = ta.trend.sma_indicator(df['volume'], window=20)
                vwap_val = calculate_vwap(df.tail(20))
                
                last = df.iloc[-1]
                candle_range = last['high'] - last['low']
                
                if candle_range == 0 or pd.isna(last['RSI']):
                    continue
                    
                upper_shadow = last['high'] - max(last['open'], last['close'])
                lower_shadow = min(last['open'], last['close']) - last['low']
                
                upper_ratio = upper_shadow / candle_range
                lower_ratio = lower_shadow / candle_range
                
                is_vol_high = last['volume'] > (last['SMA_VOL'] * VOL_MULTIPLIER)
                
                # Аналіз ПЕРЕГРІВУ (SHORT)
                is_rsi_overbought = last['RSI'] > RSI_OVERBOUGHT
                # Аналіз ПЕРЕОХОЛОДЖЕННЯ (LONG)
                is_rsi_oversold = last['RSI'] < RSI_OVERSOLD
                
                verdict = None
                
                if is_rsi_overbought or (is_rsi_oversold and is_vol_high):
                    if is_rsi_overbought and is_vol_high and upper_ratio >= MIN_UPPER_SHADOW:
                        verdict = "🔴 SHORT-СЕТАП"
                    elif is_rsi_overbought and is_vol_high:
                        verdict = "⚠️ ПЕРЕГРІВ (SHORT)"
                    elif is_rsi_oversold and is_vol_high and lower_ratio >= MIN_LOWER_SHADOW:
                        verdict = "🟢 LONG-СЕТАП"
                    elif is_rsi_oversold:
                        verdict = "❄️ ПЕРЕОХОЛОДЖЕННЯ (LONG)"
                
                if verdict:
                    vol_ratio = last['volume'] / last['SMA_VOL'] if last['SMA_VOL'] > 0 else 0
                    vwap_diff = ((last['close'] - vwap_val) / vwap_val) * 100
                    clean_ticker = symbol.split(':')[0].replace('/USDT', '')
                    
                    results.append({
                        "Токен": clean_ticker,
                        "Ціна ($)": round(last['close'], 5),
                        "RSI (4H)": round(last['RSI'], 1),
                        "Об'єм (х)": round(vol_ratio, 1),
                        "Тінь (%)": round((upper_ratio if "SHORT" in verdict else lower_ratio) * 100, 1),
                        "Відхилення VWAP (%)": f"{vwap_diff:+.1f}%",
                        "Вердикт": verdict
                    })
                time.sleep(0.04)
            except Exception:
                continue
                
        progress_bar.empty()
        status_text.empty()
        
    except Exception as e:
        st.error(f"Помилка підключення: {e}")
        
    return results

# ==========================================
# 🖥 ІНТЕРФЕЙС STREAMLIT
# ==========================================
st.set_page_config(page_title="MEXC Crypto Market Scanner", page_icon="📊", layout="wide")

st.title("📊 Двосторонній Сканер Ринку (MEXC Futures 4H)")
st.caption("Пошук перегрітих (SHORT) та переохолоджених (LONG) криптоактивів.")

if st.button("🔄 Оновити дані зараз") or 'results' not in st.session_state:
    with st.spinner("Сканування ринку MEXC..."):
        st.session_state['results'] = scan_mexc_market()
        st.session_state['last_update'] = time.strftime("%H:%M:%S")

results = st.session_state.get('results', [])
last_update = st.session_state.get('last_update', 'Ніколи')

st.write(f"**Останнє оновлення:** `{last_update}` | **Знайдено сетапів:** `{len(results)}`")

if results:
    df_results = pd.DataFrame(results)
    
    all_verdicts = ["🔴 SHORT-СЕТАП", "⚠️ ПЕРЕГРІВ (SHORT)", "🟢 LONG-СЕТАП", "❄️ ПЕРЕОХОЛОДЖЕННЯ (LONG)"]
    filter_verdict = st.multiselect(
        "Фільтр вердиктів:", 
        options=all_verdicts,
        default=all_verdicts
    )
    
    filtered_df = df_results[df_results["Вердикт"].isin(filter_verdict)]
    
    def highlight_verdict(val):
        if val == "🔴 SHORT-СЕТАП":
            return 'background-color: #ff4d4d; color: white; font-weight: bold;'
        elif val == "⚠️ ПЕРЕГРІВ (SHORT)":
            return 'background-color: #ffa64d; color: black;'
        elif val == "🟢 LONG-СЕТАП":
            return 'background-color: #2ecc71; color: white; font-weight: bold;'
        elif val == "❄️ ПЕРЕОХОЛОДЖЕННЯ (LONG)":
            return 'background-color: #3498db; color: white;'
        return ''

    styled_df = filtered_df.style.map(highlight_verdict, subset=["Вердикт"])
    
    st.dataframe(styled_df, use_container_width=True, height=450)
else:
    st.info("На даний момент виражених сигналів на ринку не виявлено.")
