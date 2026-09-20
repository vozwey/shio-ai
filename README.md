# ShioAI — настраиваемый Telegram-бот с памятью

Telegram-бот на aiogram 3 + OpenAI-совместимый API с контекстом диалога на пользователя.

## Возможности

- Все настройки задаются через `.env` (`.env.example` для шаблона)
- Работает в личных сообщениях и через **Guest Mode** (ответы через `@bot` в любом чате)
- Контекст диалога per-user хранится в оперативной памяти (последние 20 сообщений) — при перезапуске переписки теряются
- Постоянная память — единое SQLite-хранилище пар «название — значение» с тегами и опциональной привязкой к uid владельца. Личные факты о человеке пишутся с тегом (например, «Про nakiperu»), глобальные факты — без владельца. Загружается из SQLite при старте, дальше живёт в RAM
- Тул-коллинг: `search_web`, `fetch_url`, `add_memory` (с тегами и `owner_uid`), `search_memory` (поиск по диалогам + парам + тегам), `list_memory_tags` (все категории), `get_memory_by_tag` (факты категории), `list_memory`, `delete_memory`
- `search_memory(query, tag)` ищет подстроку (case-insensitive) по диалогам всех пользователей, названиям, значениям и тегам; `tag` фильтрует поиск внутри категории
- Лимит ответа: `max_tokens` через API + жёсткая обрезка до `ANSWER_MAX_CHAR` символов
- Модель сама решает, когда вызвать инструмент; после тул-кола делает ещё один проход и формирует ответ. Результаты инструментов в ответ пользователю не попадают.

## Установка

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# отредактируйте .env — обязательны TELEGRAM_BOT_TOKEN и OPENAI_API_KEY
.venv/bin/python main.py
```

## Настройки (.env)

| Параметр | По умолчанию | Описание |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | *(обязательно)* | Токен от [@BotFather](https://t.me/BotFather) |
| `OPENAI_API_KEY` | *(обязательно)* | API-ключ |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Базовый URL API (можно любой OpenAI-совместимый сервис) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Имя модели |
| `OPENAI_TEMPERATURE` | `0.7` | Температура генерации |
| `OPENAI_MAX_TOKENS` | `1500` | Лимит токенов ответа **через API** |
| `MEMORY_DB_PATH` | `memory.db` | Путь к SQLite-базе памяти (загружается при старте) |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `ANSWER_MAX_CHAR` | `4000` | Жёсткий лимит символов финального ответа |
| `CONTEXT_SIZE` | `20` | Размер per-user контекста диалога (сообщений в RAM) |
| `SNIPPET_CONTEXT_CHARS` | `25` | Символов контекста вокруг найденного слова в search_memory |
| `SEARCH_MAX_RESULTS` | `20` | Максимум сниппетов, возвращаемых search_memory |
| `TOOL_RESULT_MAX_CHAR` | `2000` | Лимит символов результата тула для модели |

> `*.env` добавлен в `.gitignore` — не коммитьте реальные ключи.

> OpenAI-совместимое API лимитирует вывод только в токенах, не в символах.
> `OPENAI_MAX_TOKENS=1500` ≈ 4000–6000 русских символов; если модель всё же вернёт больше,
> ответ будет обрезан до `ANSWER_MAX_CHAR`.

## Тесты

```bash
.venv/bin/python test_bot.py        # полный цикл: ЛС → LLM → память → контекст
.venv/bin/python test_inline.py     # inline-режим
.venv/bin/python test_dm.py         # личные сообщения
.venv/bin/python test_length.py     # лимиты длины входа/выхода
.venv/bin/python test_tools.py      # тул-коллинг: цикл, поиск, add_memory
```
