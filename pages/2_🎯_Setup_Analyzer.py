import streamlit as st
import pandas as pd
import requests
import time

# Налаштування сторінки
st.set_page_config(page_title="Детектор сетапів", layout="wide")
st.title("🎯 Детектор сетапів та маніпуляцій (CVD / SFP)")
st.caption("Повний сканер ринку ф'ючерсів MEXC у реальному часі.")

# 1. ОТРИМАННЯ ПОВНОГО СПИСКУ МОНЕТ
@st.cache_data(ttl=60)
def get_all_mexc_futures():
    try:
        url = "https://contract.mexc.com/api/v1/contract/ticker"
        res = requests.get(url, timeout=10).json()
        if res.get("success") and "data" in res:
            data = [item for item in res["data"] if item.get("symbol", "").endswith("_USDT")]
            # Сортуємо за об'ємом (найпотужніші зверху)
            data_sorted = sorted(data, key=lambda x: float(x.get("amount24", 0)), reverse=True)
            return [item["symbol"] for item in data_sorted]
    except Exception as e:
        st.error(f"Помилка зв'язку з біржею: {e}")
    return ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]

def fetch_mexc_candles(symbol, interval="Min15", limit=60):
    url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}?interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=2).json()
        if res.get("success") and "data" in res:
            data = res["data"]
            if isinstance(data, dict) and "time" in data:
                df = pd.DataFrame({
                    'time': data['time'], 'open': data['open'], 'high': data['high'],
                    'low': data['low'], 'close': data['close'], 'volume': data['vol']
                })
            else:
                df = pd.DataFrame(data)
                df = df.rename(columns={0: 'time', 1: 'open', 2: 'high', 3: 'low', 4: 'close', 5: 'volume'})
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
    except Exception:
        pass
    return None

def fetch_mexc_deals(symbol, limit=80):
    url = f"https://contract.mexc.com/api/v1/contract/deals/{symbol}?limit={limit}"
    try:
        res = requests.get(url, timeout=2).json()
        if res.get("success") and "data" in res:
            return res["data"]
    except Exception:
        pass
    return []

def analyze_sfp(df):
    if df is None or len(df) < 20:
        return "Немає"
    last = df.iloc[-1]
    prev_candles = df.iloc[-20:-1]
    recent_high = prev_candles['high'].max()
    recent_low = prev_candles['low'].min()
    
    if last['high'] > recent_high and last['close'] < recent_high:
        return "🔴 Bearish SFP (Зняття хаїв)"
    if last['low'] < recent_low and last['close'] > recent_low:
        return "🟢 Bullish SFP (Зняття лоїв)"
    return "Немає"

def calculate_cvd_delta(deals):
    if not deals:
        return 0.0, 0.0
    buy_vol, sell_vol = 0.0, 0.0
    for d in deals:
        vol = float(d.get('vol', 0))
        way = d.get('way', 1)
        if way == 1 or d.get('side') == 1:
            buy_vol += vol
        else:
            sell_vol += vol
    total = buy_vol + sell_vol
    if total == 0:
        return 0.0, 0.0
    delta_pct = ((buy_vol - sell_vol) / total) * 100
    return round(delta_pct, 1), round(buy_vol - sell_vol, 1)

# 2. ІНТЕРФЕЙС
all_pairs = get_all_mexc_futures()

st.sidebar.header("⚙️ Налаштування")
scan_scope = st.sidebar.radio(
    "Оберіть обсяг сканування:",
    [f"Усі монети ринку (~{len(all_pairs)} пар)", "ТОП-100 за об'ємом", "ТОП-50 за об'ємом"]
)

if "ТОП-50" in scan_scope:
    active_pairs = all_pairs[:50]
elif "ТОП-100" in scan_scope:
    active_pairs = all_pairs[:100]
else:
    active_pairs = all_pairs

interval = st.sidebar.selectbox("Таймфрейм", ["Min15", "Min60", "Hour4"], index=0)

st.write(f"📊 Загалом на біржі знайдено: **{len(all_pairs)}** монет. До сканування вибрано: **{len(active_pairs)}**.")

if st.button("🚀 Запустити аналіз сетапів", type="primary"):
    results = []
    
    # Створюємо елементи інтерфейсу для відстеження процесу в реальному часі
    progress_bar = st.progress(0)
    status_text = st.empty()
    table_placeholder = st.empty()
    
    total_count = len(active_pairs)
    
    for idx, sym in enumerate(active_pairs):
        # Наочно показуємо, яку саме монету зараз перевіряє сканер
        status_text.markdown(f"⏳ **Сканування ({idx+1}/{total_count})**: ` {sym} `")
        
        df = fetch_mexc_candles(sym, interval=interval)
        deals = fetch_mexc_deals(sym)
        
        sfp_signal = analyze_sfp(df)
        cvd_pct, cvd_vol = calculate_cvd_delta(deals)
        
        if df is not None and not df.empty:
            last_price = df.iloc[-1]['close']
            results.append({
                "Монета": sym,
                "Ціна": last_price,
                "Сигнал SFP": sfp_signal,
                "Дельта CVD (%)": cvd_pct,
                "Об'єм Дельти": cvd_vol
            })
            
            # Динамічно оновлюємо таблицю прямо під час процесу, щоб ти бачив результати одразу
            table_placeholder.dataframe(pd.DataFrame(results), use_container_width=True)
        
        # Руваємо шкалу прогресу від 0 до 1
        progress_bar.progress((idx + 1) / total_count)
    
    # Очищаємо текст статусу після завершення
    status_text.success(f"✅ Успішно проскановано монет: {total_count}. Знайдено результатів: {len(results)}")
