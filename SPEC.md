# SPEC.md: Blueprint Classifier API (v1.1)

## 1. Обзор системы

Микросервис (REST API) для автоматической классификации типов инженерных чертежей по ГОСТ. На основе детекции графических примитивов (полки-выноски позиций, знаки шероховатости) с помощью модели YOLOv8 сервис определяет тип документа (Сборочный чертеж или Деталь) и возвращает JSON-ответ со степенью уверенности (confidence score).

## 2. Архитектура и Стек технологий (Strict)

* **Язык:** Python 3.13
* **Фреймворк:** FastAPI (>= 0.110.0)
* **ASGI-сервер:** Uvicorn (>= 0.29.0)
* **ML-движок:** Ultralytics (>= 8.2.0), PyTorch (CPU-only для базового деплоя)
* **Обработка изображений:** python-multipart, Pillow, OpenCV-python-headless (без GUI-зависимостей)
* **Контейнеризация:** Docker, Docker Compose

---

## 3. Узкие горлышки (Bottlenecks) и их решения

### 3.1. Инициализация ML-модели (Cold Start)

* **Проблема:** Загрузка весов `.pt` в память занимает время. Если делать это при первом запросе, клиент получит таймаут.
* **Решение:** Использовать механизм **FastAPI Lifespan Events**. Модель загружается в память строго до начала приема HTTP-запросов сервером (startup) и корректно выгружается при остановке (shutdown).

### 3.2. Блокировка Event Loop при инференсе (CPU-bound)

* **Проблема:** Вызов `model.predict()` синхронен и блокирует асинхронный цикл обработки запросов.
* **Решение:** Делегирование инференса в `concurrent.futures.ThreadPoolExecutor`.
* **Детерминизм ограничения потоков:** Количество воркеров в пуле жестко ограничено значением переменной окружения `MAX_WORKERS` (по умолчанию равно количеству ядер CPU), чтобы предотвратить Out-Of-Memory (OOM) при DDOS-е запросами.

### 3.3. Утечки памяти (Memory Leaks)

* **Проблема:** Обработка тяжелых сканов (4K+) и накопление тензоров в памяти.
* **Решение:** * Потоковое чтение байт (`await file.read()`) и конвертация напрямую в numpy array/Pillow Image.
* Файлы не сохраняются на диск.
* Валидация размера файла (Content-Length) происходит *до* загрузки тела запроса в память.
* Явный вызов сборщика мусора (`gc.collect()`) после тяжелых предиктов (опционально, при долгом аптайме).



---

## 4. Конфигурация (Environment Variables)

Сервис должен конфигурироваться через файл `.env`.

| Переменная | Тип | По умолчанию | Описание |
| --- | --- | --- | --- |
| `MODEL_PATH` | string | `models/best.pt` | Путь к файлу весов YOLO |
| `MAX_FILE_SIZE_MB` | int | `15` | Максимальный размер загружаемого файла |
| `CONFIDENCE_THRESHOLD` | float | `0.4` | Минимальный порог уверенности для детекции |
| `MAX_WORKERS` | int | `4` | Лимит потоков для инференса |

---

## 5. Спецификация API (API Endpoints)

### 5.1. Проверка работоспособности (Healthcheck)

* **Method:** `GET`
* **Path:** `/health`
* **Response (200 OK):**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "version": "1.1.0"
}

```



### 5.2. Классификация чертежа

* **Method:** `POST`
* **Path:** `/api/v1/classify`
* **Content-Type:** `multipart/form-data`
* **Request Body:**
* `file`: Binary (Поддерживаемые MIME: `image/jpeg`, `image/png`, `image/webp`)



**Успешный ответ (200 OK):**

```json
{
  "success": true,
  "filename": "drawing_123.jpg",
  "prediction": {
    "document_type": "Сборочный чертеж (СБ)",
    "confidence": 0.89,
    "code": "SB"
  },
  "metrics": {
    "detected_pos_shelves": 4,
    "detected_roughness_symbols": 0,
    "inference_time_ms": 112.4
  }
}

```

**Обработка ошибок (Error Codes):**

* `400 Bad Request`: Файл не передан или поврежден.
* `413 Payload Too Large`: Размер файла превышает `MAX_FILE_SIZE_MB`.
* `415 Unsupported Media Type`: Неверный формат (передан PDF/DOCX вместо картинки).
* `422 Unprocessable Entity`: Ошибка парсинга multipart-формы.
* `503 Service Unavailable`: Модель не загружена или пул потоков переполнен.

---

## 6. Бизнес-логика интерпретации (Decision Matrix)

Агрегация найденных сущностей (где `score >= CONFIDENCE_THRESHOLD`):

1. **Сборочный чертеж (`SB`):** * Условие: `count(pos_shelf) > 3`
* Confidence: Среднее арифметическое вероятностей топ-3 самых уверенных детекций `pos_shelf`.


2. **Чертеж детали (`CD`):** * Условие: `count(pos_shelf) <= 3` AND `count(roughness) > 0`
* Confidence: Среднее арифметическое вероятностей всех найденных `roughness`.


3. **Не определено (`UNKNOWN`):** * Условие: `count(pos_shelf) <= 3` AND `count(roughness) == 0`
* Confidence: `0.0`.



---

## 7. Структура проекта (Directory Structure)

```text
blueprint-classifier/
├── src/
│   ├── api/
│   │   └── endpoints.py      # Роутеры FastAPI
│   ├── core/
│   │   ├── config.py         # Pydantic BaseSettings (парсинг .env)
│   │   └── exceptions.py     # Кастомные HTTP обработчики
│   ├── services/
│   │   └── inference.py      # Класс-обертка над YOLOv8, логика Decision Matrix
│   └── main.py               # Точка входа, Lifespan events
├── models/
│   └── best.pt               # Игнорируется в git, монтируется через volume
├── tests/
│   └── test_api.py           # Pytest интеграционные тесты
├── Dockerfile                # Инструкции сборки образа
├── docker-compose.yml        # Оркестрация
├── requirements.txt          # Жестко зафиксированные зависимости (pip freeze)
├── .env.example              # Шаблон конфига
├── .gitignore                # Игнорируемые файлы (models/, __pycache__, .env)
└── SPEC.md                   # Спецификация

```

---

## 8. Управление версиями (Git)

### 8.1. Инициализация

Репозиторий инициализирован в корне проекта. Конфигурация `.gitignore` исключает:
* `models/` — веса модели загружаются отдельно, не хранятся в VCS.
* `.env` — секреты и локальные настройки.
* `__pycache__/`, `*.pyc` — байт-код Python.

### 8.2. Конвенция коммитов

Рекомендуется формат: `<тип>(<скоуп>): <описание>`

**Типы:**
* `feat` — новый функционал
* `fix` — исправление бага
* `refactor` — рефакторинг без изменения поведения
* `docs` — документация
* `chore` — сборка, зависимости, CI/CD

**Примеры:**
```
feat(inference): implement decision matrix for SB/CD classification
fix(api): validate content-length before reading file body
docs: add API response examples to SPEC.md
chore: add Dockerfile for containerization
```

### 8.3. Ветвление

* `main` — стабильная версия, готовая к деплою.
* `dev` — основная ветка разработки.
* `feature/<name>` — отдельные фичи, мержатся в `dev` через PR.