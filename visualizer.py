import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from datetime import datetime
import os

# Настройка стиля графиков
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)
plt.rcParams['font.size'] = 10

class FlightPriceVisualizer:
    def __init__(self, output_dir='charts'):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    

    def plot_price_history(self, flight_prices, origin, destination, departure_date=None):
        """
        Строит график истории цен на рейсы
        """
        if not flight_prices:
            print("Нет данных для визуализации")
            return None

        # Конвертируем данные в DataFrame
        data = []
        for fp in flight_prices:
            data.append({
                'scraped_at': fp.scraped_at,
                'price': fp.price,
                'airline': fp.airline if fp.airline else 'Unknown',
                'departure_date': fp.departure_date,
                'stops': fp.stops if fp.stops is not None else 0,
                'flight_number': fp.flight_number if fp.flight_number else 'N/A'
            })

        df = pd.DataFrame(data)

        # Создаем figure с несколькими субплотами
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'Анализ цен на рейсы {origin} → {destination}', fontsize=16, fontweight='bold')

        # 1. График изменения минимальной цены во времени
        min_prices = df.groupby('scraped_at')['price'].min().reset_index()
        axes[0, 0].plot(min_prices['scraped_at'], min_prices['price'], marker='o', linewidth=2, markersize=8, color='#2E86AB')
        axes[0, 0].set_title('Минимальная цена по времени сбора данных', fontsize=12, fontweight='bold')
        axes[0, 0].set_xlabel('Время сбора данных', fontsize=10)
        axes[0, 0].set_ylabel('Цена (RUB)', fontsize=10)
        axes[0, 0].tick_params(axis='x', rotation=45)
        axes[0, 0].grid(True, alpha=0.3)

        # Добавляем среднюю линию
        avg_price = df['price'].mean()
        axes[0, 0].axhline(y=avg_price, color='red', linestyle='--', label=f'Средняя: {avg_price:.0f} RUB', alpha=0.7)
        axes[0, 0].legend()

        # 2. Распределение цен по авиакомпаниям (boxplot)
        top_airlines = df['airline'].value_counts().head(10).index
        df_top = df[df['airline'].isin(top_airlines)]

        if len(df_top) > 0:
            sns.boxplot(data=df_top, y='airline', x='price', ax=axes[0, 1], palette='Set2')
            axes[0, 1].set_title('Распределение цен по авиакомпаниям', fontsize=12, fontweight='bold')
            axes[0, 1].set_xlabel('Цена (RUB)', fontsize=10)
            axes[0, 1].set_ylabel('Авиакомпания', fontsize=10)
        

        # 3. Scatter plot: все цены по времени с разбивкой по авиакомпаниям
        airlines = df['airline'].unique()
        colors = sns.color_palette('husl', n_colors=min(len(airlines), 10))

        for idx, airline in enumerate(list(airlines)[:10]):
            airline_data = df[df['airline'] == airline]
            axes[1, 0].scatter(airline_data['scraped_at'], airline_data['price'], 
                             label=airline, alpha=0.6, s=100, color=colors[idx])

        axes[1, 0].set_title('Все цены по времени (топ-10 авиакомпаний)', fontsize=12, fontweight='bold')
        axes[1, 0].set_xlabel('Время сбора данных', fontsize=10)
        axes[1, 0].set_ylabel('Цена (RUB)', fontsize=10)
        axes[1, 0].tick_params(axis='x', rotation=45)
        axes[1, 0].legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        axes[1, 0].grid(True, alpha=0.3)

        # 4. Гистограмма распределения цен
        axes[1, 1].hist(df['price'], bins=30, color='#A23B72', alpha=0.7, edgecolor='black')
        axes[1, 1].axvline(df['price'].mean(), color='red', linestyle='--', linewidth=2, label=f'Среднее: {df["price"].mean():.0f} RUB')
        axes[1, 1].axvline(df['price'].median(), color='green', linestyle='--', linewidth=2, label=f'Медиана: {df["price"].median():.0f} RUB')
        axes[1, 1].set_title('Распределение цен', fontsize=12, fontweight='bold')
        axes[1, 1].set_xlabel('Цена (RUB)', fontsize=10)
        axes[1, 1].set_ylabel('Количество рейсов', fontsize=10)
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        # Сохраняем график
        filename = f"{origin}_{destination}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(self.output_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        print(f"График сохранен: {filepath}")

        #plt.show()
        
        return filepath

    def print_statistics(self, flight_prices):
        """
        Выводит статистику по ценам
        """
        if not flight_prices:
            print("Нет данных для статистики")
            return

        prices = [fp.price for fp in flight_prices]

        print("\n" + "="*60)
        print("СТАТИСТИКА ЦЕН")
        print("="*60)
        print(f"Всего рейсов найдено: {len(flight_prices)}")
        print(f"Минимальная цена: {min(prices):.2f} RUB")
        print(f"Максимальная цена: {max(prices):.2f} RUB")
        print(f"Средняя цена: {sum(prices)/len(prices):.2f} RUB")
        print(f"Медианная цена: {sorted(prices)[len(prices)//2]:.2f} RUB")

        # Статистика по авиакомпаниям
        airlines = {}
        for fp in flight_prices:
            airline = fp.airline if fp.airline else 'Unknown'
            if airline not in airlines:
                airlines[airline] = []
            airlines[airline].append(fp.price)

        print("\nЦены по авиакомпаниям:")
        for airline, prices in sorted(airlines.items(), key=lambda x: min(x[1])):
            print(f"  {airline}: от {min(prices):.2f} до {max(prices):.2f} RUB (среднее: {sum(prices)/len(prices):.2f})")

        print("="*60 + "\n")
