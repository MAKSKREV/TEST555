import asyncio
import logging
import re
import os
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
import aiohttp

# --- КОНФИГУРАЦИЯ ---
# Получаем переменные из окружения Railway
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Проверка обязательных переменных
if not all([API_ID, API_HASH, PHONE, OPENROUTER_API_KEY]):
    raise ValueError(
        "Отсутствуют обязательные переменные окружения!\n"
        "Проверьте в панели Railway:\n"
        "- TELEGRAM_API_ID\n"
        "- TELEGRAM_API_HASH\n"
        "- TELEGRAM_PHONE\n"
        "- OPENROUTER_API_KEY"
    )

# Преобразуем API_ID в int после проверки
API_ID = int(API_ID)


SOURCE_CHANNELS = [
    -1002571054985,
    -1001111641330,
    -1002544270889,
    -1003969868108, 
    -1001458367088,
    -1001161903924,

    # Добавьте сюда ID других каналов, которые нашли через @getmyid_bot
] 

DEST_CHANNEL = -1003780268513

# OpenRouter API
MODEL_NAME = os.getenv("AI_MODEL_NAME", "meta-llama/llama-3-8b-instruct")

SESSION_NAME = 'my_userbot_session'

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# Хранилище ID обработанных сообщений для защиты от дублей
processed_ids = set()

SYSTEM_PROMPT = """Ты редактор технического дайджеста про нейросети. Твоя задача — переписать новость в строгом формате.

ПРАВИЛА:
1. Удали всю рекламу: курсы, конкурсы, призывы подписаться на другие каналы.
2. Удали ссылки на другие Telegram-каналы (t.me/..., telegram.me/...), но оставь ссылки на сайты, гитхаб, статьи.
3. Определи тип новости: это инструмент/скрипт/программа для установки ИЛИ просто информационная новость?

ФОРМАТ ОТВЕТА (строго следуй структуре):
🔥 **Заголовок новости** (коротко и ясно)

💡 **Суть:** 
(1-2 предложения, о чем новость)

🛠 **Возможности:**
• (Пункт 1)
• (Пункт 2)
• (Пункт 3)


[БЛОК СЛОЖНОСТИ ТОЛЬКО ЕСЛИ ЕСТЬ ЧТО УСТАНАВЛИВАТЬ]
⚙️ **Сложность установки:** X/10 (где X — число от 0 до 10. 0 — работает в браузере, 10 — нужен сложный конфиг сервера. Если новость просто информационная — НЕ пиши этот блок).

🔗 **Источники:**
(Список полезных ссылок без телеграм-рекламы)

ВАЖНО: Не пиши никаких вступлений типа "Вот анализ". Только готовый пост.""" и пиши на русском всегда

async def process_news(text):
    """Отправляет текст на анализ AI."""
    if not text:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/my-userbot",
        "X-Title": "TG AI Digest"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Обработай эту новость:\n\n{text}"}
        ],
        "temperature": 0.3,
        "max_tokens": 800
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                data = await response.json()
                if response.status == 200:
                    return data['choices'][0]['message']['content']
                else:
                    logger.error(f"AI Error {response.status}: {data}")
                    return None
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return None

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    message = event.message
    
    # Защита от дублей
    msg_id = event.chat_id * 1000000 + message.id # Уникальный ключ
    if msg_id in processed_ids:
        logger.debug(f"Дубль сообщения {message.id}, пропускаем.")
        return
    processed_ids.add(msg_id)
    
    # Очистка старых ID (храним только последние 1000)
    if len(processed_ids) > 1000:
        processed_ids.clear()

    logger.info(f"Новый пост ID: {message.id} из канала {event.chat_id}")

    original_text = message.text or ""
    media = message.media
    
    # Проверка медиа (игнорируем WebPage)
    file_to_send = None
    if media and not isinstance(media, MessageMediaWebPage):
        if isinstance(media, (MessageMediaPhoto, MessageMediaDocument)):
            file_to_send = media

    final_text = original_text

    if original_text:
        # Фильтр явного спама перед отправкой в AI
        spam_keywords = ["курс", "обучение", "конкурс", "розыгрыш", "подпишись", "заработок"]
        if any(word in original_text.lower() for word in spam_keywords):
            # Можно решить удалять совсем или помечать. Сейчас просто обрабатываем, AI вырежет.
            pass

        logger.info("Анализ новости AI...")
        processed = await process_news(original_text)
        
        if processed:
            final_text = processed
            logger.info("Текст успешно оформлен.")
        else:
            logger.warning("AI не ответил, отправляем оригинал.")
            
    try:
        await client.send_message(DEST_CHANNEL, final_text, file=file_to_send)
        logger.info("Опубликовано в целевой канал.")
    except Exception as e:
        logger.error(f"Ошибка публикации: {e}")

async def main():
    await client.start(phone=PHONE)
    logger.info("Бот запущен. Ожидание новостей из IT и AI каналов...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем.")
