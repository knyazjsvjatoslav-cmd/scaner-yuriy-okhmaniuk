import streamlit as st
import pandas as pd
import requests

# Налаштування сторінки
st.set_page_config(page_title="Детектор Сетапів", layout="wide")
st.title("🎯 Детектор Сетапів та Маніпуляцій (CVD / SFP)")

# ---------------------------------------------------------
# 1. ФУНКЦІЇ АНАЛІЗУ (SFP, CVD, СВІЧКИ)
# ---------------------------------------------------------

def fetch_mexc_candles(symbol, interval="15m", limit=30):
    """Отримує останні свічки з ф'ючерсів MEXC"""
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}"
    try:
        res = requests.get(url, timeout=3).json()
        if res.get('success') and 'data' in res:
            data = res['data']
            df = pd.DataFrame({
                'high': [float(x) for x in data['high']],
                'low': [float(x) for x in data['low']],
                'close': [float(x) for x in data['close']],
                'open': [float(x) for x in data['open']]
            })
            return df.tail(limit)
    except Exception:
        pass
    return pd.DataFrame()

def check_sfp(df):
    """Визначає Swing Failure Pattern (ложна маніпуляція ґнотом)"""
    if len(df) < 20:
        return "NEUTRAL"
    
    prev_max = df['high'].iloc[:-1].tail(20).max()
    prev_min = df['low'].iloc[:-1].tail(20).min()
    
    curr_high = df['high'].iloc[-1]
    curr_low = df['low'].iloc[-1]
    curr_close = df['close'].iloc[-1]
    
    if curr_high > prev_max and curr_close < prev_max:
        return "SFP_HIGH"
    if curr_low < prev_min and curr_close > prev_min:
        return "SFP_LOW"
        
    return "NEUTRAL"

def get_mexc_cvd(symbol):
    """Розраховує чистий об'єм покупок/продажів за останній час"""
    url = f"https://contract.mexc.com/api/v1/contract/deals/{symbol}"
    try:
        res = requests.get(url, timeout=2).json()
        if res.get('success') and 'data' in res:
            cvd = sum([d.get('vol', 0) if d.get('side') == 1 else -d.get('vol', 0) for d in res['data']])
            return cvd
    except Exception:
        pass
    return 0

# ---------------------------------------------------------
# 2. ІНТЕРФЕЙС ТА ОБРОБКА МОНЕТ
# ---------------------------------------------------------

st.write("Аналіз якості точок входу на основі дивергенції Дельти (CVD) та маніпуляцій рівнями (SFP).")

# Список монет для перевірки (можна розширювати)
default_symbols = [
    "BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT",
    "SUI_USDT", "PEPE_USDT", "NEAR_USDT", "APT_USDT", "AVAX_USDT"
]

user_input = st.text_input("Введіть монети через кому (або залиште за замовчуванням):", value=", ".join(default_symbols))
symbols_to_check = [s.strip().upper() for s in user_input.split(",") if s.strip()]

if st.button("🚀 Запустити аналіз сетапів"):
    results = []
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(symbols_to_check):
        df_candles = fetch_mexc_candles(symbol)
        
        if not df_candles.empty:
            sfp_status = check_sfp(df_candles)
            cvd_vol = get_mexc_cvd(symbol)
            price_change = ((df_candles['close'].iloc[-1] - df_candles['open'].iloc[0]) / df_candles['open'].iloc[0]) * 100
            
            # Визначення якості сетапу
            verdict = "⚪ Спокійно"
            if sfp_status == "SFP_HIGH" and cvd_vol < 0:
                verdict = "🔥 A+ SHORT (SFP High + Bearish CVD)"
            elif sfp_status == "SFP_LOW" and cvd_vol > 0:
                verdict = "🚀 A+ LONG (SFP Low + Bullish CVD)"
            elif price_change > 3.0 and cvd_vol < -5000:
                verdict = "⚠️ Пастка покупців (CVD Drop)"
            elif sfp_status == "SFP_HIGH":
                verdict = "⚠️ SFP High (Очікує CVD)"
                
            results.append({
                "Монета": symbol,
                "Зміна (15m) %": round(price_change, 2),
                "CVD Delta": round(cvd_vol, 2),
                "SFP Статус": sfp_status,
                "Вердикт": verdict
            })
            
        progress_bar.progress((i + 1) / len(symbols_to_check))
        
    if results:
        df_res = pd.DataFrame(results)
        
        # Фільтр у боковій панелі
        selected_verdicts = st.sidebar.multiselect(
            "Фільтр за вердиктом:",
            options=df_res["Вердикт"].unique(),
            default=df_res["Вердикт"].unique()
        )
        
        filtered_df = df_res[df_res["Вердикт"].isin(selected_verdicts)]
        st.dataframe(filtered_df, use_container_width=True)
    else:
        st.warning("Не вдалося отримати дані по вибраних монетах.")
