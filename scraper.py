from botasaurus.browser import browser, Driver
from datetime import datetime, date
import time
import re

class AviasalesScraper:
    BASE_URL = "https://www.aviasales.ru"

    @staticmethod
    def build_search_url(origin, destination, departure_date):
        """
        Создает URL для поиска рейсов на Aviasales
        departure_date: объект datetime.date или строка в формате YYYY-MM-DD
        """
        if isinstance(departure_date, date):
            date_str = departure_date.strftime('%d%m')
        else:
            date_obj = datetime.strptime(departure_date, '%Y-%m-%d').date()
            date_str = date_obj.strftime('%d%m')
        
        return f"{AviasalesScraper.BASE_URL}/search/{origin}{date_str}{destination}1"

    @browser(
        reuse_driver=True, 
        wait_for_complete_page_load=False,
        block_images=True,
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    def scrape_flights(driver: Driver, data):
        """
        Скрапит цены на рейсы с Aviasales.ru
        data: словарь с ключами origin, destination, departure_date
        """
        origin = data['origin']
        destination = data['destination']
        departure_date = data['departure_date']

        url = AviasalesScraper.build_search_url(origin, destination, departure_date)
        print(f"Открываю страницу: {url}")

        try:
            driver.get(url, timeout=120)
        except Exception as e:
            print(f"⚠️  Ошибка при загрузке страницы: {e}")
            print("Пробую продолжить работу...")

        # Ждем загрузки результатов
        driver.sleep(15)

        # Прокручиваем страницу для загрузки всех результатов
        try:
            for _ in range(3):
                driver.run_js("window.scrollTo(0, document.body.scrollHeight);")
                driver.sleep(1)
        except Exception as e:
            print(f"⚠️  Не удалось прокрутить страницу: {e}")

        flights = []

        try:
            # Ищем карточки рейсов
            selectors = [
                '[data-test-id^="direct-schedule-group-"]',
                '[data-test-id*="direct-ticket"]',
                '[class*="__XM25TpwN6UmJJLL"]',
                '[data-test-id="flight-card"]',
                '.product-list__item',
                '[class*="snippet"]'
            ]
            
            flight_cards = []
            for selector in selectors:
                flight_cards = driver.select_all(selector)
                if flight_cards:
                    print(f"Найдено карточек рейсов: {len(flight_cards)} (селектор: {selector})")
                    break

            if not flight_cards:
                print("❌ Карточки рейсов не найдены")
                return []
            
            for idx, card in enumerate(flight_cards[:20]):
                try:
                    flight_data = AviasalesScraper._parse_flight_card(card, origin, destination, departure_date)
                    if flight_data and flight_data.get('price'):
                        # Конвертируем datetime в строку для JSON
                        flight_data_json = flight_data.copy()
                        if 'scraped_at' in flight_data_json and isinstance(flight_data_json['scraped_at'], datetime):
                            flight_data_json['scraped_at'] = flight_data_json['scraped_at'].isoformat()

                        # Используем строковую версию даты для JSON
                        if 'departure_date_str' in flight_data_json:
                            flight_data_json['departure_date'] = flight_data_json['departure_date_str']
                            del flight_data_json['departure_date_str']

                        flights.append(flight_data_json)
                        print(f"Рейс {idx + 1}: {flight_data.get('airline', 'N/A')} - {flight_data['price']} руб.")
                except Exception as e:
                    print(f"Ошибка при парсинге карточки рейса {idx + 1}: {e}")
                    continue

        except Exception as e:
            print(f"Ошибка при поиске карточек рейсов: {e}")

        print(f"Всего собрано рейсов: {len(flights)}")
        return flights

    @staticmethod
    def _parse_flight_card(card, origin, destination, departure_date):
        """
        Парсит информацию из карточки рейса
        """
        # Конвертируем дату в строку для JSON сериализации
        if isinstance(departure_date, date):
            departure_date_str = departure_date.isoformat()
        else:
            departure_date_str = departure_date
            departure_date = datetime.strptime(departure_date, '%Y-%m-%d').date()

        flight_data = {
            'origin': origin,
            'destination': destination,
            'departure_date': departure_date,  # Оставляем объект date для БД
            'departure_date_str': departure_date_str,  # Добавляем строку для JSON
            'scraped_at': datetime.utcnow()
        }

        try:
            card_text = card.text

            # Получаем цену - ищем числа перед ₽ или руб, удаляем все виды пробелов
            price_match = re.search(r'(\d[\d\s\u202f\xa0]*)\s*[₽руб]', card_text)
            if price_match:
                price_str = price_match.group(1).replace(' ', '').replace('\u202f', '').replace('\xa0', '').strip()
                if price_str:
                    flight_data['price'] = float(price_str)
                    flight_data['currency'] = 'RUB'

            # Если не нашли, пробуем альтернативный метод
            if 'price' not in flight_data:
                clean_text = card_text.replace(' ', '').replace('\xa0', '').replace('\u202f', '')
                numbers = re.findall(r'\d{3,}', clean_text)
                if numbers:
                    flight_data['price'] = float(max(numbers, key=lambda x: int(x)))
                    flight_data['currency'] = 'RUB'

            # Авиакомпания
            airlines_keywords = ['Аэрофлот', 'S7', 'Победа', 'Уральские авиалинии', 'Utair', 
                               'Nordwind', 'Smartavia', 'Азимут', 'Red Wings', 'Россия']

            for airline in airlines_keywords:
                if airline.lower() in card_text.lower():
                    flight_data['airline'] = airline
                    break
                            
            if 'airline' not in flight_data:
                flight_data['airline'] = 'Unknown'

            # Время вылета и прилета
            times = re.findall(r'\b(\d{1,2}:\d{2})\b', card_text)
            if len(times) >= 2:
                flight_data['departure_time'] = times[0]
                flight_data['arrival_time'] = times[1]

            # Продолжительность
            duration_match = re.search(r'(\d+\s*ч\s*\d*\s*мин|\d+ч|\d+\s*ч)', card_text)
            if duration_match:
                flight_data['duration'] = duration_match.group(1).strip()

            # Пересадки
            if 'прям' in card_text.lower() or 'без пересадок' in card_text.lower():
                flight_data['stops'] = 0
            else:
                stops_match = re.search(r'(\d+)\s*пересад', card_text.lower())
                if stops_match:
                    flight_data['stops'] = int(stops_match.group(1))

        except Exception as e:
            print(f"Ошибка при извлечении данных: {e}")

        return flight_data if 'price' in flight_data else None