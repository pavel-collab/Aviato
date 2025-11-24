Подъем докер-контейнера
```
docker-compose up -d
```

Подключение к докеру из консоли
```
docker exec -it <container-id> /bin/bash
```

Запуск сбора данных
```
python3 main.py --origin MOW --destination LED --date 2025-12-15 --action scrape
```

Визуализация
```
python3 main.py --origin MOW --destination LED --date 2025-12-15 --action vizualizе # или both для одновременного сбора и визуализации
```

Непрерывный мониторинг
```
python3 main.py --origin MOW --destination LED --date 2025-12-15 --monitor --iterval 30
```