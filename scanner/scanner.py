import time
import requests
import ccxt

# ==========================================
# 1. НАЛАШТУВАННЯ ТЕЛЕГРАМ ТА MEXC
# ==========================================
TELEGRAM_TOKEN = 8842488494:AAFfZPxqiF-pwrh1lpbmvQKNcIK_0kJZE1o
CHAT_ID = 504656312

ALERT_COOLDOWN = 7200  # Затримка між сповіщеннями на одну монету (2 години)
last_alerts = {}

# Підключаємося до ф'ючерсів MEXC
exchange = ccxt.mexc({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
    }
})

# Список монет на MEXC для моніторингу
SYMBOLS = [
    'CME/USDT:USDT',
    'PUMP/USDT:USDT',
    'SPELL/USDT:USDT',
    'QNT/USDT:USDT',
    'W/USDT:USDT',
    'BIGTIME/USDT:USDT',
    'ORCA/USDT:USDT',
    'PYTH/USDT:USDT'
]

# ==========================================
# 2. ФУНКЦІЇ АНАЛІЗУ
# ==========================================

def send_telegram_alert(symbol, signal_type, score, rsi, shadow, vwap_dev, price):
    emoji = "🟢" if signal_type == "LONG" else "🔴"
    message = (
        f"{emoji} <b>СЕТАП: {signal_type} — {symbol}</b>\n\n"
        f"💰 <b>Поточна ціна:</b> ${price}\n"
        f"🎯 <b>Оцінка якості:</b> {score}/7 балів\n"
        f"📊 <b>RSI (4H):</b> {rsi:.1f}\n"
        f"🕯 <b>Тінь свічки:</b> {shadow:.1f}%\n"
        f"📈 <b>Відхилення VWAP:</b> {vwap_dev:.1f}%\n\n"
        f"💡 <i>Підтверджено злам структури (BOS) на 15M!</i>"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Помилка відправки в Telegram: {e}")

def check_structure_bos(candles_15m, signal_type):
    if not candles_15m or len(candles_15m) < 5:
        return False
    last_close = candles_15m[-1][4]
    if signal_type == "LONG":
        prev_highs = [c[2] for c in candles_15m[-4:-1]]
        return last_close > max(prev_highs)
    elif signal_type == "SHORT":
        prev_lows = [c[3] for c in candles_15m[-4:-1]]
        return last_close < min(prev_lows)
    return False

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def analyze_symbol(symbol):
    try:
        ohlcv_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=30)
        ohlcv_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=10)
        
        if not ohlcv_4h or len(ohlcv_4h) < 15:
            return

        last_4h = ohlcv_4h[-1]
        open_p, high_p, low_p, close_p = last_4h[1], last_4h[2], last_4h[3], last_4h[4]
        
        candle_range = high_p - low_p if high_p != low_p else 1e-8
        upper_shadow = ((high_p - max(open_p, close_p)) / candle_range) * 100
        lower_shadow = ((min(open_p, close_p) - low_p) / candle_range) * 100

        closes_4h = [c[4] for c in ohlcv_4h]
        rsi_4h = calculate_rsi(closes_4h)

        vol_sum = sum(c[5] for c in ohlcv_4h[-6:])
        vwap_dev = ((close_p - (sum(c[4] * c[5] for c in ohlcv_4h[-6:]) / vol_sum)) / (sum(c[4] * c[5] for c in ohlcv_4h[-6:]) / vol_sum)) * 100 if vol_sum > 0 else 0.0

        # Розрахунок балів
        long_score = 0
        if rsi_4h < 25: long_score += 2
        elif rsi_4h < 32: long_score += 1
        if lower_shadow > 35: long_score += 2
        if vwap_dev < -15: long_score += 1
        if check_structure_bos(ohlcv_15m, "LONG"): long_score += 2

        short_score = 0
        if rsi_4h > 75: short_score += 2
        elif rsi_4h > 68: short_score += 1
        if upper_shadow > 35: short_score += 2
        if vwap_dev > 15: short_score += 1
        if check_structure_bos(ohlcv_15m, "SHORT"): short_score += 2

        print(f"[{symbol}] RSI: {rsi_4h:.1f} | L_Shadow: {lower_shadow:.1f}% | U_Shadow: {upper_shadow:.1f}% | VWAP: {vwap_dev:.1f}% | Score L/S: {long_score}/{short_score}")

        current_time = time.time()

        if long_score >= 5 and (symbol not in last_alerts or (current_time - last_alerts[symbol]) > ALERT_COOLDOWN):
            send_telegram_alert(symbol, "LONG", long_score, rsi_4h, lower_shadow, vwap_dev, close_p)
            last_alerts[symbol] = current_time

        elif short_score >= 5 and (symbol not in last_alerts or (current_time - last_alerts[symbol]) > ALERT_COOLDOWN):
            send_telegram_alert(symbol, "SHORT", short_score, rsi_4h, upper_shadow, vwap_dev, close_p)
            last_alerts[symbol] = current_time

    except Exception as e:
        print(f"Помилка {symbol}: {e}")

def main():
    print("🚀 Сканер MEXC запущено...")
    while True:
        for symbol in SYMBOLS:
            analyze_symbol(symbol)
            time.sleep(0.5)
        time.sleep(60)

if __name__ == "__main__":
    main()
