import time
import requests
import ccxt

# ==============================================================================
# 1. НАЛАШТУВАННЯ ТЕЛЕГРАМ ТА MEXC
# ==============================================================================
TELEGRAM_TOKEN = '6842438494:AAEkKx19-owm0lpbmwOWcIK_8k3Z21o'
TELEGRAM_CHAT_ID = '594656312'

# Інтервал між повторними сповіщеннями для однієї монети (наприклад, 2 години = 7200 сек)
СПОВІЩЕННЯ_ПЕРЕРВА = 7200  
останні_сповіщення = {}

# Підключаємося до ф'ючерсів MEXC
обмін = ccxt.mexc({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap'  # Отримуємо ф'ючерсні ринки
    }
})

def send_telegram_message(text):
    """Надсилання сповіщення в Телеграм"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Помилка надсилання в Telegram: {e}")

# ==============================================================================
# 2. АВТОМАТИЧНЕ ОТРИМАННЯ ВСІХ МОНЕТ З MEXC
# ==============================================================================
def get_all_mexc_symbols():
    """Завантажує ВСІ ф'ючерсні монети USDT з MEXC"""
    try:
        markets = обмін.load_markets()
        symbols = [
            symbol for symbol, data in markets.items()
            if data.get('swap') and data.get('linear') and symbol.endswith(':USDT')
        ]
        print(f"Успішно завантажено монет для сканування: {len(symbols)}")
        return symbols
    except Exception as e:
        print(f"Помилка при отриманні списку монет: {e}")
        return []

# ==============================================================================
# 3. АНАЛІЗ ТА ОСНОВНИЙ ЦИКЛ
# ==============================================================================
def analyze_symbol(symbol):
    """Функція аналізу однієї монети (твоя логіка сигналів)"""
    # Тут виконується перевірка обсягів / ціни / індикатора
    pass

def main():
    print("Сканер MEXC запущено у 24/7 режимі...")
    send_telegram_message("🚀 <b>Сканер MEXC успішно запущено на Render!</b>\nМоніторинг усіх монет розпочато.")

    while True:
        symbols = get_all_mexc_symbols()
        
        if not symbols:
            print("Не вдалося отримати список монет, повторна спроба через 60 сек...")
            time.sleep(60)
            continue

        for symbol in symbols:
            try:
                # Перевіряємо та аналізуємо монету
                analyze_symbol(symbol)
                time.sleep(0.1)  # Невелика пауза, щоб не перевищити ліміти API MEXC
            except Exception as e:
                print(f"Помилка при аналізі {symbol}: {e}")
                continue

        # Пауза 60 секунд перед наступним колом перевірки всіх монет
        time.sleep(60)

if __name__ == "__main__":
    main()
