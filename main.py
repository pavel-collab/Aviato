#!/usr/bin/env python3

"""
Приложение для мониторинга цен на авиабилеты с Aviasales.ru
"""
import argparse
from datetime import datetime, timedelta
from models import Database
from scraper import AviasalesScraper
from visualizer import FlightPriceVisualizer
import time

def scrape_and_save(origin, destination, departure_date, db):
    """
    Скрапит рейсы и сохраняет их в базу данных
    """
    print(f"\n{'='*60}")
    print(f"Начинаю сбор данных о рейсах")
    print(f"Маршрут: {origin} → {destination}")
    print(f"Дата вылета: {departure_date}")
    print(f"{'='*60}\n")

    try:
        # Формируем данные для передачи в scraper
        search_params = {
            'origin': origin,
            'destination': destination,
            'departure_date': departure_date
        }

        # Скрапим рейсы
        flights = AviasalesScraper.scrape_flights(search_params)
        
        if not flights:
            print("❌ Рейсы не найдены. Возможные причины:")
            print("   - Неверные коды городов (используйте IATA коды, например: MOW, LED)")
            print("   - Aviasales изменил структуру сайта")
            print("   - Нет доступных рейсов на эту дату")
            return 0

        # Сохраняем в базу данных
        saved_count = 0
        for flight in flights:
            try:
                db.add_flight_price(flight)
                saved_count += 1
            except Exception as e:
                print(f"⚠️  Ошибка при сохранении рейса: {e}")

        print(f"\n✅ Успешно сохранено рейсов: {saved_count} из {len(flights)}")
        return saved_count

    except Exception as e:
        print(f"❌ Ошибка при сборе данных: {e}")
        import traceback
        traceback.print_exc()
        return 0

def visualize_prices(origin, destination, departure_date, db, visualizer):
    """
    Визуализирует историю цен
    """
    print(f"\n{'='*60}")
    print(f"Получаю историю цен из базы данных")
    print(f"{'='*60}\n")

    try:
        # Получаем историю цен
        flight_prices = db.get_price_history(origin, destination, departure_date)

        if not flight_prices:
            print("❌ Нет данных в базе для визуализации")
            print("   Сначала выполните сбор данных командой: --action scrape")
            return

        print(f"✅ Найдено записей в базе: {len(flight_prices)}")

        # Выводим статистику
        visualizer.print_statistics(flight_prices)
        
        # Строим графики
        visualizer.plot_price_history(flight_prices, origin, destination, departure_date)
    except Exception as e:
        print(f"❌ Ошибка при визуализации: {e}")
        import traceback
        traceback.print_exc()

def monitor_prices(origin, destination, departure_date, db, visualizer, interval_minutes=60):
    """
    Мониторит цены с заданным интервалом
    """
    print(f"\n{'='*60}")
    print(f"РЕЖИМ МОНИТОРИНГА")
    print(f"Маршрут: {origin} → {destination}")
    print(f"Дата вылета: {departure_date}")
    print(f"Интервал сбора: {interval_minutes} минут")
    print(f"{'='*60}\n")

    iteration = 1
    try:
        while True:
            print(f"\n🔄 Итерация #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Собираем данные
            saved_count = scrape_and_save(origin, destination, departure_date, db)
            if saved_count > 0:
                print(f"✅ Итерация #{iteration} завершена успешно")

            iteration += 1
            # Ждем следующей итерации
            print(f"\n⏳ Ожидание {interval_minutes} минут до следующего сбора...")
            time.sleep(interval_minutes * 60)

    except KeyboardInterrupt:
        print("\n\n🛑 Мониторинг остановлен пользователем")
        print(f"Всего выполнено итераций: {iteration - 1}")

def main():
    parser = argparse.ArgumentParser(
        description='Мониторинг цен на авиабилеты с Aviasales.ru',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Собрать данные о рейсах Москва → Санкт-Петербург на 2025-01-15
  python main.py --origin MOW --destination LED --date 2025-01-15 --action scrape
  
  # Визуализировать историю цен
  python main.py --origin MOW --destination LED --date 2025-01-15 --action visualize
  
  # Запустить мониторинг с интервалом 30 минут
  python main.py --origin MOW --destination LED --date 2025-01-15 --action monitor --interval 30
  
  # Собрать данные и сразу визуализировать
  python main.py --origin MOW --destination LED --date 2025-01-15 --action both

Популярные IATA коды городов России:
  MOW - Москва, LED - Санкт-Петербург, SVX - Екатеринбург
  KZN - Казань, OVB - Новосибирск, AER - Сочи
        """
    )

    parser.add_argument('--origin', required=True, help='IATA код города отправления (например: MOW)')
    parser.add_argument('--destination', required=True, help='IATA код города назначения (например: LED)')
    parser.add_argument('--date', required=True, help='Дата вылета в формате YYYY-MM-DD')
    parser.add_argument('--action', choices=['scrape', 'visualize', 'monitor', 'both'], 
                       default='both', help='Действие: scrape (собрать), visualize (показать графики), monitor (мониторинг), both (собрать и показать)')
    parser.add_argument('--interval', type=int, default=60, 
                       help='Интервал между сборами данных в минутах (только для режима monitor)')

    args = parser.parse_args()

    # Валидация даты
    try:
        departure_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        if departure_date < datetime.now().date():
            print(f"⚠️  Предупреждение: указанная дата ({args.date}) в прошлом")
    except ValueError:
        print(f"❌ Неверный формат даты. Используйте формат YYYY-MM-DD")
        return

    # Инициализация
    print("🚀 Запуск приложения мониторинга цен на авиабилеты")
    print("📊 Инициализация базы данных...")

    try:
        db = Database()
        db.create_tables()
        print("✅ База данных готова")
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")
        print("   Убедитесь, что PostgreSQL запущен (docker-compose up -d)")
        return    

    visualizer = FlightPriceVisualizer()

    # Выполнение действий
    if args.action == 'scrape':
        scrape_and_save(args.origin, args.destination, args.date, db)
        
    elif args.action == 'visualize':
        visualize_prices(args.origin, args.destination, args.date, db, visualizer)

    elif args.action == 'monitor':
        monitor_prices(args.origin, args.destination, args.date, db, visualizer, args.interval)

    elif args.action == 'both':
        saved = scrape_and_save(args.origin, args.destination, args.date, db)
        if saved > 0:
            visualize_prices(args.origin, args.destination, args.date, db, visualizer)

    print("\n✨ Готово!")

if __name__ == '__main__':
    main()