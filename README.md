# Blueprint Classifier API

> **Внимание!** Модель обучена на сыром датасете и требует дообучения для повышения точности классификации. Результаты на новых данных могут отличаться от ожидаемых.

Микросервис для автоматической классификации типов инженерных чертежей по ГОСТ с помощью компьютерного зрения.

## Обзор

Сервис анализирует графические примитивы на чертеже — **полки-выноски позиций** и **знаки шероховатости** — и на основе детекции модели YOLOv8 определяет тип документа:

| Тип документа | Код | Условие |
|---------------|-----|---------|
| Сборочный чертеж | `SB` | Обнаружено более 3 полок-выносок |
| Чертеж детали | `CD` | ≤ 3 полок-выносок и ≥ 1 знак шероховатости |
| Не определено | `UNKNOWN` | Не хватает данных для классификации |

## Стек технологий

- **Python 3.13** + **FastAPI** (>= 0.110.0)
- **YOLOv8** (Ultralytics >= 8.2.0) для детекции объектов
- **OpenCV** + **Pillow** для обработки изображений
- **Pydantic Settings** для управления конфигурацией
- **Docker** + **Docker Compose** для контейнеризации

## Быстрый старт

### 1. Клонирование и настройка

```bash
git clone https://github.com/your-org/blueprint-classifier.git
cd blueprint-classifier
cp .env.example .env
```

### 2. Запуск через Docker (рекомендуется)

```bash
docker-compose up --build
```

Сервис будет доступен по адресу `http://localhost:8000`.

### 3. Запуск локально

```bash
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

> Убедитесь, что файл модели `models/best.pt` находится в корне проекта.

## Конфигурация

Переменные окружения задаются в файле `.env`:

| Переменная | Тип | По умолчанию | Описание |
|------------|-----|--------------|----------|
| `MODEL_PATH` | string | `models/best.pt` | Путь к весам YOLO |
| `MAX_FILE_SIZE_MB` | int | `15` | Максимальный размер файла (MB) |
| `CONFIDENCE_THRESHOLD` | float | `0.4` | Минимальный порог уверенности |
| `MAX_WORKERS` | int | `4` | Лимит потоков для инференса |

## API

### Healthcheck

```
GET /health
```

```json
{
  "status": "healthy",
  "model_loaded": true,
  "version": "1.1.0"
}
```

### Классификация чертежа

```
POST /api/v1/classify
Content-Type: multipart/form-data
```

**Параметры:**
- `file` — изображение (`image/jpeg`, `image/png`, `image/webp`)

**Пример ответа (200 OK):**

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

**Коды ошибок:**

| Код | Описание |
|-----|----------|
| `400` | Файл не передан или поврежден |
| `413` | Размер файла превышает лимит |
| `415` | Неподдерживаемый формат изображения |
| `422` | Ошибка парсинга multipart-формы |
| `503` | Модель не загружена |

## Примеры использования

### cURL

```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -F "file=@drawing.png"
```

### Python

```python
import requests

with open("drawing.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/classify",
        files={"file": f}
    )
print(response.json())
```

## Структура проекта

```
blueprint-classifier/
├── src/
│   ├── api/
│   │   └── endpoints.py      # Роутеры FastAPI
│   ├── core/
│   │   ├── config.py         # Настройки (Pydantic BaseSettings)
│   │   └── exceptions.py     # Кастомные HTTP-исключения
│   ├── services/
│   │   └── inference.py      # Классификатор (YOLOv8 + Decision Matrix)
│   └── main.py               # Точка входа, Lifespan
├── models/
│   └── best.pt               # Веса модели (не в git)
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Архитектура

```
┌──────────────┐     ┌─────────────┐     ┌──────────────────┐
│   Клиент     │────▶│  FastAPI     │────▶│ BlueprintClassifier│
│              │◀────│  (Router)    │◀────│   (YOLOv8)       │
└──────────────┘     └─────────────┘     └──────────────────┘
                           │                       │
                     Валидация              ThreadPoolExecutor
                     MIME, размер           (изолированный пул)
```

- **Lifespan** загружает модель в память при старте и выгружает при остановке
- **ThreadPoolExecutor** предотвращает блокировку Event Loop при инференсе
- **Валидация размера** через `Content-Length` — до чтения тела запроса
