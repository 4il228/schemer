# PLAN.md: Декомпозиция микросервиса Blueprint Classifier API

## Фаза 1: Базовая инфраструктура и Конфигурация

**Цель:** Создать структуру директорий проекта, зафиксировать зависимости и реализовать модуль управления конфигурацией через переменные окружения.
**Контекст (CoT):** Прежде чем писать бизнес-логику, нам нужен жесткий каркас. Использование `pydantic-settings` позволит валидировать типы переменных окружения при старте приложения, предотвращая ошибки типа "ожидали int, получили string".
**Действия:**

1. Создать дерево директорий:
* `src/api/`
* `src/core/`
* `src/services/`
* `models/`
* `tests/`


2. Создать файл `requirements.txt` со следующими строгими зависимостями:
* `fastapi>=0.110.0`
* `uvicorn>=0.29.0`
* `pydantic-settings`
* `python-multipart`
* `Pillow`
* `ultralytics>=8.2.0`
* `opencv-python-headless`


3. Создать файл `.env.example` с базовыми значениями: `MODEL_PATH=models/best.pt`, `MAX_FILE_SIZE_MB=15`, `CONFIDENCE_THRESHOLD=0.4`, `MAX_WORKERS=4`.
4. Создать файл `src/core/config.py`. Реализовать класс `Settings`, унаследованный от `BaseSettings`, включающий поля:
* `model_path: str`
* `max_file_size_mb: int`
* `confidence_threshold: float`
* `max_workers: int`
**Критерии приемки:**



* Структура папок создана.
* `config.py` успешно читает данные из `.env` файла или использует дефолтные значения, если файла нет.

---

## Фаза 2: Глобальная обработка ошибок (Exceptions)

**Цель:** Создать стандартизированные ответы для ожидаемых HTTP-ошибок.
**Контекст (CoT):** Чтобы API отвечал предсказуемо (например, при загрузке 100 МБ файла или PDF вместо JPG), необходимо вынести логику ошибок в отдельный слой. Это очистит код роутеров.
**Действия:**

1. Создать файл `src/core/exceptions.py`.
2. Реализовать классы кастомных исключений:
* `UnsupportedMediaTypeError` (наследует `HTTPException`, status_code=415, detail="Неверный формат. Ожидается JPEG, PNG, WEBP").
* `PayloadTooLargeError` (наследует `HTTPException`, status_code=413, detail="Размер файла превышает лимит").
* `ModelNotLoadedError` (наследует `HTTPException`, status_code=503, detail="ML модель недоступна").
**Критерии приемки:**



* Файл `exceptions.py` содержит классы исключений, готовые к импорту в роутеры.

---

## Фаза 3: ML-Сервис (Ядро бизнес-логики)

**Цель:** Реализовать класс-обертку для модели YOLOv8, исполняющий инференс в изолированном пуле потоков и агрегирующий результаты по матрице решений.
**Контекст (CoT):** YOLO — синхронная библиотека. Вызов `model()` заблокирует FastAPI. Поэтому мы инициализируем `ThreadPoolExecutor` при создании класса и запускаем инференс через `loop.run_in_executor`.
**Действия:**

1. Создать файл `src/services/inference.py`.
2. Импортировать `ultralytics.YOLO`, `concurrent.futures.ThreadPoolExecutor`, `asyncio`, `PIL.Image`, `io`.
3. Реализовать класс `BlueprintClassifier`:
* **`__init__(self, model_path, confidence_threshold, max_workers)`:** загружает модель (`YOLO(model_path)`), сохраняет порог, инициализирует `ThreadPoolExecutor(max_workers=max_workers)`.
* **`_predict_sync(self, image_bytes)`:** (Синхронный метод). Читает байты в `PIL.Image`. Вызывает модель. Возвращает сырые боксы, где `score >= confidence_threshold`.
* **`_apply_decision_matrix(self, boxes)`:**
* Считает кол-во `pos_shelf` (класс 0) и `roughness` (класс 1).
* *Логика СБ:* Если `pos_shelf` > 3 -> Тип: `Сборочный чертеж (СБ)`, Code: `SB`, Confidence: среднее от топ-3 `pos_shelf`.
* *Логика ДТ:* Если `pos_shelf` <= 3 И `roughness` > 0 -> Тип: `Чертеж детали (CD)`, Code: `CD`, Confidence: среднее всех `roughness`.
* *Иначе:* Тип: `Не определено`, Code: `UNKNOWN`, Confidence: 0.0.


* **`predict_async(self, image_bytes)`:** (Асинхронный метод). Вызывает `_predict_sync` внутри `asyncio.get_running_loop().run_in_executor(...)`. Измеряет время выполнения (`time.perf_counter()`). Передает результат в `_apply_decision_matrix`. Возвращает итоговый словарь (prediction, metrics).
* **`unload(self)`:** Закрывает `ThreadPoolExecutor`, очищает память модели.
**Критерии приемки:**



* Класс полностью инкапсулирует работу с YOLO и матрицу решений.
* Класс использует пулы потоков для предотвращения блокировки основного Event Loop.

---

## Фаза 4: Реализация API Эндпоинтов

**Цель:** Создать роутеры FastAPI для обработки входящих HTTP-запросов, валидации файлов и вызова ML-сервиса.
**Контекст (CoT):** Эндпоинты должны быть "тонкими". Вся валидация файла (MIME, размер) происходит до его полной выгрузки в RAM.
**Действия:**

1. Создать файл `src/api/endpoints.py`.
2. Импортировать `APIRouter`, `UploadFile`, `Request`, классы ошибок из `src.core.exceptions`, класс настроек из `src.core.config`.
3. Создать `router = APIRouter()`.
4. Реализовать `GET /health`:
* Возвращает `{"status": "healthy", "model_loaded": bool(request.app.state.classifier), "version": "1.1.0"}`.


5. Реализовать `POST /api/v1/classify`:
* Принимает `file: UploadFile`.
* *Валидация MIME:* проверить `file.content_type` на вхождение в `['image/jpeg', 'image/png', 'image/webp']`. Иначе поднять `UnsupportedMediaTypeError`.
* *Валидация размера:* получить размер из `request.headers.get("content-length")`. Если превышает `settings.max_file_size_mb * 1024 * 1024`, поднять `PayloadTooLargeError`.
* *Чтение:* `bytes_data = await file.read()`.
* *Инференс:* Получить экземпляр классификатора из `request.app.state.classifier`. Вызвать `await classifier.predict_async(bytes_data)`.
* *Ответ:* Сформировать JSON согласно спецификации (поля `success`, `filename`, `prediction`, `metrics`).
**Критерии приемки:**



* Роутеры корректно обрабатывают и валидируют файлы.
* Логика ML не смешивается с логикой HTTP.

---

## Фаза 5: Сборка приложения (Main & Lifespan)

**Цель:** Собрать приложение FastAPI, настроить Lifespan для загрузки/выгрузки модели и подключить роутеры.
**Контекст (CoT):** Lifespan events пришли на смену устаревшим `@app.on_event("startup")`. Загрузка весов YOLO происходит здесь, чтобы при первом запросе клиента модель уже была в ОЗУ сервера.
**Действия:**

1. Создать файл `src/main.py`.
2. Использовать `contextlib.asynccontextmanager`.
3. Реализовать функцию `lifespan(app: FastAPI)`:
* *Startup:* Инстанцировать `BlueprintClassifier` с параметрами из `Settings`. Записать инстанс в `app.state.classifier`.
* `yield` (приложение работает).
* *Shutdown:* Вызвать метод `unload()` у классификатора. Удалить его из `state`. Вызвать `gc.collect()`.


4. Инициализировать `app = FastAPI(lifespan=lifespan)`.
5. Подключить роутер: `app.include_router(endpoints.router)`.
**Критерии приемки:**

* Приложение успешно запускается через Uvicorn.
* Модель загружается в память ровно один раз при старте.

---

## Фаза 6: Docker Контейнеризация

**Цель:** Упаковать микросервис в Docker для изолированного запуска в любой среде.
**Контекст (CoT):** OpenCV требует системных библиотек (`libgl1`, `libglib2.0-0`), которых нет в базовых slim-образах Python. Их нужно установить через `apt-get`.
**Действия:**

1. Создать `Dockerfile`:
* Базовый образ `python:3.13-slim`.
* Установить системные зависимости: `apt-get update && apt-get install -y libgl1 libglib2.0-0`.
* Скопировать `requirements.txt`, установить зависимости без кэша (`pip install --no-cache-dir`).
* Скопировать директорию `src/`.
* Команда запуска: `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]`.


2. Создать `docker-compose.yml`:
* Сервис `api`.
* Сборка из контекста `.`.
* Проброс портов `8000:8000`.
* Монтирование вольюма для папки с весами: `./models:/app/models`.
* Подключение `.env` файла.
**Критерии приемки:**



* Контейнер собирается без ошибок и запускается через `docker-compose up`.