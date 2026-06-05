import asyncio
import logging
import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
import aiohttp

# --- КОНФИГУРАЦИЯ ---
API_ID = int(os.getenv("TELEGRAM_API_ID", "25316255"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "caacc56333e6d2445732ea75eddd56e5")
PHONE = os.getenv("TELEGRAM_PHONE", "+79686041007")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
STRING_SESSION = os.getenv("STRING_SESSION")

if not OPENROUTER_API_KEY:
    print("⚠️ OPENROUTER_API_KEY не установлен! AI-обработка новостей работать не будет.")

SOURCE_CHANNELS = [
    -1002571054985, -1001111641330, -1002544270889,
    -1003969868108, -1001458367088, -1001161903924,
]
DEST_CHANNEL = -1003780268513
MODEL_NAME = os.getenv("AI_MODEL_NAME", "meta-llama/llama-3-8b-instruct")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Автоматический выбор: StringSession для Railway / файл для локального ПК
if STRING_SESSION:
    logger.info("✅ Режим Railway: используется StringSession из окружения")
    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
else:
    logger.info("✅ Режим ПК: используется локальный файл сессии")
    client = TelegramClient('my_userbot_session', API_ID, API_HASH)

processed_ids = set()

SYSTEM_PROMPT = """Ты редактор технического дайджеста про нейросети и кибербезопасность. Твоя задача — переписать новость в строгом формате.

ПРАВИЛА:
1. Удали всю рекламу: курсы, конкурсы, призывы подписаться на другие каналы.
2. Удали ссылки на другие Telegram-каналы (t.me/..., telegram.me/...), но оставь ссылки на сайты, гитхаб, статьи.
3. Определи тип новости: это инструмент/скрипт/программа для установки ИЛИ просто информационная новость?
4. ВСЕГДА пиши ответ ПОЛНОСТЬЮ на русском языке.

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

ВАЖНО: В самом конце поста ОБЯЗАТЕЛЬНО добавь строку:
Помощь и обратная связь в этом боте @DEXQsquad_bot

НЕ пиши никаких вступлений типа "Вот анализ", "Конечно", "Вот готовый пост". Только сам пост в указанном формате."""

async def process_news(text):
    if not text or not OPENROUTER_API_KEY:
        return text

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
                json=payload, headers=headers
            ) as response:
                data = await response.json()
                if response.status == 200:
                    return data['choices'][0]['message']['content']
                else:
                    logger.error(f"AI Error {response.status}: {data}")
                    return text
    except Exception as e:
        logger.error(f"Connection error to AI: {e}")
        return text

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    message = event.message
    msg_id = event.chat_id * 1000000 + message.id
    if msg_id in processed_ids:
        return
    processed_ids.add(msg_id)
    if len(processed_ids) > 1000:
        processed_ids.clear()

    logger.info(f"Новый пост ID: {message.id} из канала {event.chat_id}")
    original_text = message.text or ""
    media = message.media
    file_to_send = None
    if media and not isinstance(media, MessageMediaWebPage):
        if isinstance(media, (MessageMediaPhoto, MessageMediaDocument)):
            file_to_send = media

    final_text = original_text
    if original_text:
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
    logger.info("🚀 Бот запущен. Ожидание новостей из IT и AI каналов...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем.")
