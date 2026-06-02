# Infra AI News Pipeline

Автоматическая публикация ИТ-новостей в Telegram-канал и группу ВКонтакте.

Отдаёшь ссылку на статью — получаешь готовый пост с иллюстрацией в обоих каналах.

## Как работает

```
URL статьи
    |
    v
[1] Загрузка страницы
    |
    v
[2] Claude Sonnet — генерация текста поста (отдельно для Telegram и VK)
    |
    v
[3] ProxyAPI — генерация иллюстрации по описанию из JSON
    |
    v
[4] Telegram Bot API — фото + текст в канал
    |
    v
[5] VK API — текстовый пост в группу
```

Весь контент (JSON + PNG) сохраняется в папку `post/` — можно проверить перед публикацией.

## Стек

| Компонент | Инструмент |
|-----------|------------|
| Генерация текста | Claude Sonnet 4.6 через [ProxyAPI](https://proxyapi.ru) |
| Генерация картинки | gpt-image-1-mini через ProxyAPI |
| Telegram | Bot API (`sendPhoto` + `sendMessage`) |
| VK | VK API v5.199 (`wall.post`) |
| Язык | Python 3.13+ |

## Установка

```bash
pip install requests python-dotenv vk_api
```

## Настройка

Скопируйте `.env.example` в `.env` и заполните переменные:

```bash
cp .env.example .env
```

### Получение токенов

**ProxyAPI** — регистрация на [proxyapi.ru](https://proxyapi.ru), ключ в личном кабинете.

**VK** — создайте сообщество, перейдите в `Управление → Работа с API → Создать ключ`. Нужны права: `wall`, `photos`.

**Telegram** — создайте бота через [@BotFather](https://t.me/BotFather), добавьте его администратором в канал.

## Использование

### Основной сценарий

```bash
# Опубликовать сразу
python publish.py --url "https://example.com/article"

# Запланировать публикацию
python publish.py --url "https://example.com/article" --schedule 2026-06-03T12:00:00Z

# Проверить без публикации (генерирует файлы, но не публикует)
python publish.py --url "https://example.com/article" --dry-run
```

### Переиспользование готовых файлов

```bash
# Пропустить генерацию, использовать существующий JSON и картинку
python publish.py --json post/2026-06-03-article.json --image post/2026-06-03-article.png

# Пересоздать картинку, но использовать готовый JSON
python publish.py --json post/2026-06-03-article.json
```

### Отдельные модули

Каждый скрипт работает независимо:

```bash
# Только Telegram
python tg_post.py --json post/article.json --image post/article.png
python tg_post.py --content "Текст поста"

# Только VK
python vk_post.py --json post/article.json
python vk_post.py --content "Текст поста" --schedule 2026-06-03T12:00:00Z

# Только картинка
python generate_image_from_json.py --json post/article.json --output post/article.png
```

## Структура проекта

```
publish.py                    # Главный оркестратор
tg_post.py                    # Публикация в Telegram
vk_post.py                    # Публикация в VK
generate_image_from_json.py   # Генерация иллюстрации
infra-ai-news-to-social.md    # Промпт-скилл для генерации текста
.env.example                  # Шаблон переменных окружения
post/                         # Генерируемые файлы (в .gitignore)
  YYYY-MM-DD-slug.json        # Контент поста
  YYYY-MM-DD-slug.png         # Иллюстрация
```

## Формат JSON-файла

Скрипт генерирует файл в папке `post/` с таким содержимым:

```json
{
  "schema_version": "social-content/v1",
  "source": {
    "title": "Название статьи",
    "url": "https://...",
    "published_at": "2026-06-03"
  },
  "image_prompt": "Описание для генерации иллюстрации",
  "platforms": {
    "telegram": {
      "content": "Текст поста для Telegram"
    },
    "vk": {
      "content": "Текст поста для VK"
    }
  }
}
```

Файл можно редактировать вручную перед публикацией, затем запустить:
```bash
python publish.py --json post/file.json --image post/file.png
```

## Ограничения

- **VK + картинки** — community-токен VK не поддерживает загрузку фото через API (ошибка 27). Посты публикуются без картинки. Для фото нужен пользовательский токен (`VK_USER_TOKEN`).
- **Telegram + длинный текст** — если текст превышает 1024 символа, картинка и текст отправляются двумя отдельными сообщениями.
- **Планирование** — `--schedule` работает через `time.sleep`. Для долгосрочного планирования лучше использовать cron или Task Scheduler.
