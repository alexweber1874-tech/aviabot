import logging
import sqlite3
from datetime import datetime
import asyncio
import aiohttp

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8740250657:AAHGO_2o6r1oG67JP-hH0Hff3PWEgjaF3RE"
API_TOKEN = "a3f46b78429c1caf68d66faa2caeffaf"
CHAT_ID = 1785348212

ORIGIN_CITIES = ["MOW", "KZN"]
DESTINATION_CITY = "BEG"
DEPARTURE_DATE = "2027-08-19"
RETURN_DATE = "2027-09-02"
MAX_PRICE = 50000

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS flights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route TEXT, date TEXT, price REAL, airline TEXT,
            flight_number TEXT, baggage TEXT, found_at TEXT,
            last_price REAL, last_check TEXT
        )
    ''')
    conn.commit()
    conn.close()

def check_flight_exists(route, date, flight_number):
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor()
    cursor.execute('SELECT price, last_price FROM flights WHERE route=? AND date=? AND flight_number=?', (route, date, flight_number))
    result = cursor.fetchone()
    conn.close()
    return result

def add_flight(route, date, price, airline, flight_number, baggage):
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO flights (route, date, price, airline, flight_number, baggage, found_at, last_price, last_check) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (route, date, price, airline, flight_number, baggage, datetime.now().isoformat(), price, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_flight_price(route, date, flight_number, new_price):
    conn = sqlite3.connect('flights.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE flights SET last_price=?, last_check=? WHERE route=? AND date=? AND flight_number=?',
        (new_price, datetime.now().isoformat(), route, date, flight_number))
    conn.commit()
    conn.close()

# --- ПОИСК БИЛЕТОВ (РЕАЛЬНЫЙ API) ---
async def search_flights():
    logging.info("Запуск поиска билетов через Aviasales API...")
    found_new, price_dropped = [], []
    
    async with aiohttp.ClientSession() as session:
        for origin in ORIGIN_CITIES:
            url = "https://api.travelpayouts.com/v1/prices/cheap"
            params = {"origin": origin, "destination": DESTINATION_CITY, "depart_date": DEPARTURE_DATE[:7], "return_date": RETURN_DATE[:7], "token": API_TOKEN}
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "data" in data:
                            for date_key, flight_info in data["data"].items():
                                if isinstance(flight_info, dict):
                                    price = flight_info.get("price", 0)
                                    airline = flight_info.get("airline", "Unknown")
                                    flight_number = f"{airline}-{date_key}"
                                    baggage = "20kg"
                                    
                                    if 0 < price <= MAX_PRICE:
                                        route = f"{origin}-{DESTINATION_CITY}"
                                        existing = check_flight_exists(route, date_key, flight_number)
                                        if not existing:
                                            add_flight(route, date_key, price, airline, flight_number, baggage)
                                            found_new.append({"route": route, "date": date_key, "price": price, "airline": airline, "flight_number": flight_number, "baggage": baggage})
                                        else:
                                            if price < existing[0]:
                                                update_flight_price(route, date_key, flight_number, price)
                                                price_dropped.append({"route": route, "date": date_key, "price": price, "airline": airline, "flight_number": flight_number, "baggage": baggage})
            except Exception as e:
                logging.error(f"Ошибка API: {e}")
    return found_new, price_dropped

# --- ОТПРАВКА УВЕДОМЛЕНИЙ ---
async def send_notifications(found_new, price_dropped):
    if not found_new and not price_dropped:
        logging.info("Новых предложений не найдено")
        return
    
    message = "🔔 Уведомление о билетах\n\n"
    if found_new:
        message += "🆕 Новые маршруты:\n" + "".join([f"✈️ {f['airline']} ({f['flight_number']})\n📍 {f['route']} | 📅 {f['date']}\n💰 {f['price']} руб | 🧳 {f['baggage']}\n\n" for f in found_new])
    if price_dropped:
        message += "📉 Цена снизилась:\n" + "".join([f"✈️ {f['airline']} ({f['flight_number']})\n📍 {f['route']} | 📅 {f['date']}\n💰 {f['price']} руб | 🧳 {f['baggage']}\n\n" for f in price_dropped])
    
    async with aiohttp.ClientSession() as session:
        await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": CHAT_ID, "text": message})
    logging.info("Уведомление отправлено в Telegram")

# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    init_db()
    logging.info("Запуск автоматического поиска...")
    found_new, price_dropped = await search_flights()
    await send_notifications(found_new, price_dropped)
    logging.info("Поиск завершён")

if __name__ == "__main__":
    asyncio.run(main())
