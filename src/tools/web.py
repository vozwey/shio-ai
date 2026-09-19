from ddgs import DDGS
import trafilatura
from src.tools.registry import tool


@tool("Поиск ссылок в интернете. Возвращает список заголовков и прямых URL. Используй короткие ключевые слова для запроса.")
def search_web(query: str, max_results: int = 5) -> str:
    try:
        results = DDGS().text(
            query, region="ru-ru", max_results=max_results, backend="auto"
        )
        if not results:
            results = DDGS().text(
                query,
                region="ru-ru",
                max_results=max_results,
                backend="duckduckgo",
            )
        if not results:
            return "По запросу ничего не найдено."

        output = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Без названия")
            url = r.get("href") or r.get("link") or r.get("url")
            if url:
                output.append(f"{i}. {title}\nURL: {url}")

        return "\n\n".join(output) if output else "По запросу ничего не найдено."
    except Exception as e:
        return f"Ошибка поиска: {e}"


@tool("Загружает страницу по URL и читает её текстовое содержимое. Используй после search_web, выбрав наиболее подходящую ссылку.")
def fetch_url(url: str, max_chars: int = 4000) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return "Не удалось загрузить страницу."

        text = trafilatura.extract(
            downloaded, include_links=False, include_images=False
        )
        if not text or not text.strip():
            return "Не удалось извлечь полезный текст со страницы."

        if len(text) > max_chars:
            text = text[:max_chars] + "...[обрезано]"

        return text
    except Exception as e:
        return f"Ошибка при загрузке URL: {e}"
