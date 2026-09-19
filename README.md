# ShioAI — настраиваемый Telegram-бот с памятью

Telegram-бот на aiogram 3 + OpenAI-совместимый API с контекстом диалога на пользователя.

## Возможности

- Все настройки задаются через `.env` (`.env.example` для шаблона)
- Работает в личных сообщениях и через **inline-режим** (`@bot ваш запрос`)
- Хранит контекст диалога per-user в SQLite (последние 20 сообщений), так что модель «помнит» предыдущие реплики
- Лимит ответа: `max_tokens` через API + жёсткая обрезка до `ANSWER_MAX_CHAR` символов
- Тул-коллинг: поиск в интернете через 4get, долговременная память (факты/воспоминания о пользователе)
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
| `MEMORY_DB_PATH` | `memory.db` | Путь к SQLite-базе памяти |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `ANSWER_MAX_CHAR` | `4000` | Жёсткий лимит символов финального ответа |
| `FOURGET_BASE_URL` | `https://4get.joygnu.org` | Базовый URL поисковика 4get |
| `TOOL_MAX_ITERATIONS` | `5` | Максимум тул-коллов за запрос (защита от цикла) |
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
