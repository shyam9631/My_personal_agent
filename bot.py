"""
Telegram bot — this is the chat interface. Works identically on:
- Telegram app on your phone
- Telegram Desktop / Web on your laptop
Same bot, same conversation, no separate setup needed per device.
"""
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

import config
from agent import run_agent

logging.basicConfig(level=logging.INFO)

# simple in-memory per-chat history (resets on restart — fine for now)
chat_histories = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey Shyam, I'm your assistant. Ask me anything, or tell me to check your mail."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text

    history = chat_histories.get(chat_id, [])
    reply_text = run_agent(user_text, history=history)

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply_text})
    chat_histories[chat_id] = history[-10:]  # keep last 10 messages only

    await update.message.reply_text(reply_text)


def main():
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Add it to your .env file "
            "(get one from @BotFather on Telegram)."
        )

    # A fresh event loop is required when this runs inside a background
    # thread (e.g. from main.py on Render) rather than the main thread.
    asyncio.set_event_loop(asyncio.new_event_loop())

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running. Open Telegram and message your bot.")
    app.run_polling()


if __name__ == "__main__":
    main()