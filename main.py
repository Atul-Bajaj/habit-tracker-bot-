import json
import datetime
import asyncio
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# === CONFIG ===
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
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
        data["groups"][group_id] = {"habits": {}, "completion_data": {}, "streaks": {}}
        save_data()

def create_done_keyboard(group_id, habit):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Mark '{habit}' as Done", callback_data=f"{group_id}:{habit}")
    ]])

# === COMMANDS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)
    await update.message.reply_text(
        "👋 Hello! I'm your Habit Tracker bot.\n"
        "Use /addhabit <habit> <HH:MM> to start tracking!"
    )

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

async def list_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)

    habits = data["groups"][group_id]["habits"]
    if not habits:
        await update.message.reply_text("No habits set. Use /addhabit to add one!")
        return

    msg = "📝 *Current Habits:*\n"
    for habit, time in habits.items():
        msg += f"- {habit} at {time}\n"

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

    # Update streak
    user_streak = group["streaks"].setdefault(user, {}).setdefault(habit, 0)
    group["streaks"][user][habit] = user_streak + 1

    save_data()

    await context.bot.send_message(
        chat_id=group_id,
        text=f"🎉 *{user}* completed *{habit}* today! 🔥 Streak: *{group['streaks'][user][habit]} days!*",
        parse_mode='Markdown'
    )

    await query.edit_message_text(f"✅ You marked *{habit}* as done! 🔥 Streak: {group['streaks'][user][habit]} days!", parse_mode='Markdown')

# === REMINDER SYSTEM ===

async def send_reminder(bot, group_id, habit):
    await bot.send_message(
        chat_id=group_id,
        text=f"⏰ Reminder: Time to *{habit}*!",
        reply_markup=create_done_keyboard(group_id, habit),
        parse_mode='Markdown'
    )

async def schedule_reminders(app):
    while True:
        now = datetime.datetime.now().strftime("%H:%M")
        for group_id, group_data in data["groups"].items():
            for habit, reminder_time in group_data["habits"].items():
                if now == reminder_time:
                    await send_reminder(app.bot, group_id, habit)
        await asyncio.sleep(60)  # Check every minute

# === NEW GROUP WELCOME ===

async def new_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.message.chat_id)
    ensure_group(group_id)
    await update.message.reply_text(
        "👋 Hello! I'm your Habit Tracker bot.\n"
        "Use /addhabit <habit> <HH:MM> to start tracking habits in this group!"
    )

# === MAIN ===

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addhabit", add_habit))
    app.add_handler(CommandHandler("listhabits", list_habits))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_group_handler))

    # Start reminder scheduler
    app.create_task(schedule_reminders(app))

    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    import nest_asyncio

    nest_asyncio.apply()

    asyncio.get_event_loop().run_until_complete(main())

