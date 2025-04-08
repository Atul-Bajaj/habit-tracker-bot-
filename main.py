from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import datetime
import os

# In-memory data storage (will reset if the server restarts)
user_data = {}

# Environment variables
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Use /done to mark your habit as complete.")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    date = datetime.date.today().isoformat()

    if user not in user_data:
        user_data[user] = []
    if date in user_data[user]:
        await update.message.reply_text("You've already marked it complete today! ✅")
        return

    user_data[user].append(date)

    # Notify group
    bot: Bot = context.bot
    await bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=f"🎉 {user} has completed their habit today! Keep it up, team!"
    )

    await update.message.reply_text(f"✅ Well done, {user}! I've marked your habit for today.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    streak = len(user_data.get(user, []))
    await update.message.reply_text(f"{user}, your current streak is: {streak} day(s)! 🔥")

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("done", done))
app.add_handler(CommandHandler("stats", stats))

if __name__ == '__main__':
    print("Bot is running...")
    app.run_polling()
