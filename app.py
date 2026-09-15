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
RSI_OVERBOUGHT = 70
RSI_WARMING = 60         # Зона підготовки до перегріву
MIN_UPPER_SHADOW = 0.30

# Пороги Переохолодження (LONG)
RSI_OVERSOLD = 32
RSI_COOLING = 40         # Зона підготовки до переохолодження
MIN_LOWER_SHADOW = 0.30

# Загальні
VOL_MULTIPLIER_STRONG = 1.8
VOL_MULTIPLIER_EARLY = 1.3

def calculate_vwap(df):
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    return (typical_price * df['volume']).sum() / df['volume'].sum()

def scan_mexc_market():
    exchange = ccxt.mexc({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    overheated = []
    oversold = []
    
    try:
        markets = exchange.load_markets()
        usdt_pairs = [
            symbol for symbol, market in markets.items()
            if market.get('swap') and market.get('settle') == 'USDT' and market.get('active')
        ]
        
        total_pairs = len(usdt_pairs)
        if total_pairs == 0:
            st.error("Не вдалося отримати список монет з MEXC.")
            return overheated, oversold

        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, symbol in enumerate(usdt_pairs):
            clean_ticker = symbol.split(':')[0].replace('/USDT', '')
            status_text.text(f"Сканування {idx+1} з {total_pairs}: {clean_ticker}")
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
                
                vol_ratio = last['volume'] / last['SMA_VOL'] if last['SMA_VOL'] > 0 else 0
                vwap_diff = ((last['close'] - vwap_val) / vwap_val) * 100
                rsi_val = round(last['RSI'], 1)
                
                # --- АНАЛІЗ ПЕРЕГРІВУ ТА ГАРЯЧИХ МОНЕТ ---
                if rsi_val >= RSI_WARMING:
                    if rsi_val >= RSI_OVERBOUGHT:
                        if vol_ratio >= VOL_MULTIPLIER_STRONG and upper_ratio >= MIN_UPPER_SHADOW:
                            verdict = "🔴 SHORT-СЕТАП"
                        elif vol_ratio >= VOL_MULTIPLIER_STRONG:
                            verdict = "⚠️ СТИСНЕННЯ / СПЛЕСК"
                        else:
                            verdict = "🔥 ПЕРЕГРІВ (RSI ≥ 70)"
                    else:  # RSI 60–69
                        if vol_ratio >= VOL_MULTIPLIER_EARLY:
                            verdict = "⚡ ПОТЕНЦІЙНИЙ ПЕРЕГРІВ"
                        else:
                            verdict = "📈 РОЗГРІВ (RSI 60+)"
                            
                    overheated.append({
                        "Токен": clean_ticker,
                        "Ціна ($)": round(last['close'], 5),
                        "RSI (4H)": rsi_val,
                        "Об'єм (х)": round(vol_ratio, 1),
                        "Верхня тінь (%)": round(upper_ratio * 100, 1),
                        "VWAP (%)": f"{vwap_diff:+.1f}%",
                        "Вердикт": verdict
                    })

                # --- АНАЛІЗ ПЕРЕОХОЛОДЖЕННЯ ТА ХОЛОДНИХ МОНЕТ ---
                if rsi_val <= RSI_COOLING:
                    if rsi_val <= RSI_OVERSOLD:
                        if vol_ratio >= VOL_MULTIPLIER_STRONG and lower_ratio >= MIN_LOWER_SHADOW:
                            verdict = "🟢 LONG-СЕТАП"
                        elif vol_ratio >= VOL_MULTIPLIER_STRONG:
                            verdict = "⚠️ КАПІТУЛЯЦІЯ / СПЛЕСК"
                        else:
                            verdict = "❄️ ПЕРЕОХОЛОДЖЕННЯ (RSI ≤ 32)"
                    else:  # RSI 33–40
                        if vol_ratio >= VOL_MULTIPLIER_EARLY:
                            verdict = "⚡ ПОТЕНЦІЙНЕ ПЕРЕОХОЛОДЖЕННЯ"
                        else:
                            verdict = "📉 ОХОЛОДЖЕННЯ (RSI 40-)"
                            
                    oversold.append({
                        "Токен": clean_ticker,
                        "Ціна ($)": round(last['close'], 5),
                        "RSI (4H)": rsi_val,
                        "Об'єм (х)": round(vol_ratio, 1),
                        "Нижня тінь (%)": round(lower_ratio * 100, 1),
                        "VWAP (%)": f"{vwap_diff:+.1f}%",
                        "Вердикт": verdict
                    })
                    
                time.sleep(0.015)
            except Exception:
                continue
                
        progress_bar.empty()
        status_text.empty()
        
    except Exception as e:
        st.error(f"Помилка підключення: {e}")
        
    return overheated, oversold

# ==========================================
# 🖥 ІНТЕРФЕЙС STREAMLIT
# ==========================================
st.set_page_config(page_title="MEXC Full Market Scanner", page_icon="⚡", layout="wide")

st.title("⚡ Повний Сканер Ринку MEXC Futures")
st.caption("Пошук готових сетапів та монет на стадії розігріву / охолодження.")

if st.button("🔄 Оновити дані зараз") or 'overheated' not in st.session_state:
    with st.spinner("Сканування ВСІХ монет MEXC..."):
        overheated, oversold = scan_mexc_market()
        st.session_state['overheated'] = overheated
        st.session_state['oversold'] = oversold
        st.session_state['last_update'] = time.strftime("%H:%M:%S")

overheated = st.session_state.get('overheated', [])
oversold = st.session_state.get('oversold', [])
last_update = st.session_state.get('last_update', 'Ніколи')

st.write(f"**Останнє оновлення:** `{last_update}` | Гарячі/Перегріті: `{len(overheated)}` | Холодні/Переохолоджені: `{len(oversold)}`")

tab1, tab2 = st.tabs(["🔥 Гарячі / Перегріті", "❄️ Холодні / Переохолоджені"])

with tab1:
    if overheated:
        df_over = pd.DataFrame(overheated).sort_values(by="RSI (4H)", ascending=False)
        
        def highlight_short(val):
            if val == "🔴 SHORT-СЕТАП":
                return 'background-color: #ff4d4d; color: white; font-weight: bold;'
            elif "СПЛЕСК" in val:
                return 'background-color: #ffa64d; color: black;'
            elif "ПОТЕНЦІЙНИЙ" in val:
                return 'background-color: #ffe0b2; color: black; font-weight: bold;'
            return 'background-color: #fff3e0; color: black;'

        st.dataframe(df_over.style.map(highlight_short, subset=["Вердикт"]), use_container_width=True, height=500)
    else:
        st.info("Гарячих монет з RSI ≥ 60 зараз не знайдено.")

with tab2:
    if oversold:
        df_under = pd.DataFrame(oversold).sort_values(by="RSI (4H)", ascending=True)
        
        def highlight_long(val):
            if val == "🟢 LONG-СЕТАП":
                return 'background-color: #2ecc71; color: white; font-weight: bold;'
            elif "СПЛЕСК" in val:
                return 'background-color: #3498db; color: white;'
            elif "ПОТЕНЦІЙНЕ" in val:
                return 'background-color: #b3e5fc; color: black; font-weight: bold;'
            return 'background-color: #e1f5fe; color: black;'

        st.dataframe(df_under.style.map(highlight_long, subset=["Вердикт"]), use_container_width=True, height=500)
    else:
        st.info("Холодних монет з RSI ≤ 40 зараз не знайдено.")
