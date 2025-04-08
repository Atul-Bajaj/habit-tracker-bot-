import json
import datetime
import asyncio
import os
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# === CONFIG ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATA_FILE = 'data.json'

# === DATA HANDLING ===

def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"groups": {}}

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

data = load_data()

def get_today():
    return datetime.date.today().isoformat()

# === HELPERS ===

def ensure_group(group_id):
    if group_id not in data["groups"]:
        data["groups"][group_id] = {"habits": {}, "completion_data": {}}
        save_data()

def create_done_keyboard(group_id, habit):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Mark '{habit}' as Done", callback_data=f"{group_id}:{habit}")
    ]])

def get_progress_bar(progress):
    total_blocks = 10
    filled_blocks = int(progress * total_blocks)
    empty_blocks = total_blocks - filled_blocks
    return "█" * filled_blocks + "░" * empty_blocks

# === COMMANDS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)
    await update.message.reply_text(
        "👋 Hello! I'm your Habit Tracker bot.\n"
        "Use /addhabit <habit> <HH:MM> to start tracking!\n"
        "Use /removehabit <habit> to remove a habit.\n"
        "Use /streaks to see group progress!\n"
        "Stay consistent 💪"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addhabit <habit> <HH:MM>")
        return

    habit = context.args[0]
    time = context.args[1]

    data["groups"][group_id]["habits"][habit] = time
    save_data()

    await update.message.reply_text(f"✅ Habit *{habit}* added with reminder at {time}!", parse_mode='Markdown')

async def remove_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)

    if not context.args:
        await update.message.reply_text("Usage: /removehabit <habit>")
        return

    habit = context.args[0]

    if habit in data["groups"][group_id]["habits"]:
        del data["groups"][group_id]["habits"][habit]
        save_data()
        await update.message.reply_text(f"🗑️ Habit *{habit}* removed!", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"Habit *{habit}* not found.", parse_mode='Markdown')

async def list_streaks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)

    group = data["groups"][group_id]
    today = get_today()
    habits = group["habits"]
    completions = group.get("completion_data", {}).get(today, {})

    if not habits:
        await update.message.reply_text("No habits set. Use /addhabit to add one!")
        return

    msg = "📊 *Today's Progress:*\n\n"
    for habit in habits:
        total = len(completions.get(habit, []))
        progress = total / 5  # 5 users = full progress bar, you can adjust
        progress_bar = get_progress_bar(min(progress, 1))
        msg += f"*{habit}*: {progress_bar} ({total} completed)\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

# === BUTTON HANDLER ===

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split(":")
    group_id, habit = data_parts[0], data_parts[1]

    user = query.from_user.first_name
    today = get_today()

    ensure_group(group_id)

    group = data["groups"][group_id]
    day_data = group["completion_data"].setdefault(today, {})
    day_data.setdefault(habit, [])

    if user in day_data[habit]:
        await query.edit_message_text(f"✅ You already completed *{habit}* today!", parse_mode='Markdown')
        return

    day_data[habit].append(user)
    save_data()

    progress = len(day_data[habit]) / 5  # Simple progress (5 users = full)
    progress_bar = get_progress_bar(min(progress, 1))

    await context.bot.send_message(
        chat_id=group_id,
        text=f"🎉 *{user}* completed *{habit}* today!\nProgress: {progress_bar} ({len(day_data[habit])} completed)",
        parse_mode='Markdown'
    )

    await query.edit_message_text(f"✅ You marked *{habit}* as done!\nProgress: {progress_bar}", parse_mode='Markdown')

# === REMINDER SYSTEM ===

async def send_reminder(bot, group_id, habit):
    await bot.send_message(
        chat_id=group_id,
        text=f"⏰ *Reminder:* Time to *{habit}*! Stay on track 💪",
        reply_markup=create_done_keyboard(group_id, habit),
        parse_mode='Markdown'
    )

async def send_daily_summary(bot, group_id):
    group = data["groups"][group_id]
    today = get_today()
    completions = group.get("completion_data", {}).get(today, {})
    habits = group["habits"]

    if not habits:
        return

    msg = "🌟 *Daily Summary*\n\n"
    for habit in habits:
        done_users = completions.get(habit, [])
        progress = len(done_users) / 5
        progress_bar = get_progress_bar(min(progress, 1))
        msg += f"*{habit}*: {progress_bar} ({len(done_users)} completed)\n"

    await bot.send_message(
        chat_id=group_id,
        text=msg,
        parse_mode='Markdown'
    )

async def schedule_reminders(app):
    print("🚀 Reminder scheduler started!")
    while True:
        now = datetime.datetime.now().strftime("%H:%M")
        current_hour = datetime.datetime.now().strftime("%H:%M")

        for group_id, group_data in data["groups"].items():
            # Reminders
            for habit, reminder_time in group_data["habits"].items():
                if now == reminder_time:
                    await send_reminder(app.bot, group_id, habit)

            # Daily Summary at 20:00
            if current_hour == "20:00":
                await send_daily_summary(app.bot, group_id)

        await asyncio.sleep(60)  # Check every minute

# === NEW GROUP WELCOME ===

async def new_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.message.chat_id)
    ensure_group(group_id)
    await update.message.reply_text(
        "👋 Hello! I'm your Habit Tracker bot.\n"
        "Use /addhabit <habit> <HH:MM> to start tracking habits in this group!\n"
        "Use /removehabit <habit> to remove one.\n"
        "Use /streaks to see progress!"
    )

# === MAIN ===

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addhabit", add_habit))
    app.add_handler(CommandHandler("removehabit", remove_habit))
    app.add_handler(CommandHandler("streaks", list_streaks))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_group_handler))

    # Start reminder scheduler
    async def safe_scheduler():
        while True:
            try:
                await schedule_reminders(app)
            except Exception as e:
                print(f"Scheduler crashed with error: {e}. Restarting...")
                await asyncio.sleep(1)

    app.create_task(safe_scheduler())

    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()

    asyncio.run(main())
