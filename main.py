import json
import datetime
import asyncio
import os
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import firebase_admin
from firebase_admin import credentials, firestore

# === CONFIG ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Initialize Firebase Admin SDK
firebase_credentials = json.loads(os.getenv('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred)

# Firestore client
db = firestore.client()

# === DATA HANDLING ===

def get_today():
    return datetime.date.today().isoformat()

# === HELPERS ===

def ensure_group(group_id):
    # Ensure a group exists in Firestore
    group_ref = db.collection('groups').document(group_id)
    if not group_ref.get().exists:
        group_ref.set({"habits": {}, "completion_data": {}, "streaks": {}})

def create_done_keyboard(group_id, habit):
    # Creates the inline button for marking the habit as done
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Mark '{habit}' as Done", callback_data=f"{group_id}:{habit}")
    ]])

def get_progress_bar(progress):
    # Returns a visual progress bar
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
    
    # Add habit to Firestore
    add_habit_to_firebase(group_id, habit, time)
    
    await update.message.reply_text(f"✅ Habit *{habit}* added with reminder at {time}!", parse_mode='Markdown')

def add_habit_to_firebase(group_id, habit_name, reminder_time):
    # Add habit to Firestore under the 'habits' collection
    habits_ref = db.collection('groups').document(group_id).collection('habits')
    habits_ref.add({
        'habit_name': habit_name,
        'reminder_time': reminder_time
    })

async def remove_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)

    if not context.args:
        await update.message.reply_text("Usage: /removehabit <habit>")
        return

    habit = context.args[0]

    # Remove the habit from Firestore
    group_ref = db.collection('groups').document(group_id)
    habits_ref = group_ref.collection('habits')
    habit_to_delete = habits_ref.where('habit_name', '==', habit).stream()

    for doc in habit_to_delete:
        habits_ref.document(doc.id).delete()
    
    await update.message.reply_text(f"🗑️ Habit *{habit}* removed!", parse_mode='Markdown')

async def list_streaks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = str(update.effective_chat.id)
    ensure_group(group_id)

    group_ref = db.collection('groups').document(group_id)
    streaks_ref = group_ref.collection('streaks')

    streaks = streaks_ref.stream()

    msg = "📊 *Current Streaks for Each Habit* 📊\n\n"
    for streak in streaks:
        streak_data = streak.to_dict()
        msg += f"*{streak.id}*: {streak_data['streak']} days\n"
    
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

    group_ref = db.collection('groups').document(group_id)
    completions_ref = group_ref.collection("completion_data").document(today)

    habit_completions = completions_ref.get().to_dict()
    if habit_completions is None:
        habit_completions = {}

    habit_completions[habit] = habit_completions.get(habit, [])
    if user not in habit_completions[habit]:
        habit_completions[habit].append(user)
        completions_ref.set(habit_completions)

    # Update Streaks
    streaks_ref = group_ref.collection("streaks").document(habit)
    streak_data = streaks_ref.get().to_dict()
    current_streak = streak_data['streak'] if streak_data else 0
    new_streak = current_streak + 1 if len(habit_completions[habit]) > 0 else 0
    streaks_ref.set({"streak": new_streak})

    await query.edit_message_text(f"✅ You marked *{habit}* as done!")
    await context.bot.send_message(
        chat_id=group_id,
        text=f"🎉 *{user}* completed *{habit}* today! Current streak: {new_streak} days",
        parse_mode='Markdown'
    )

# === REMINDER SYSTEM ===

async def send_reminder(bot, group_id, habit):
    await bot.send_message(
        chat_id=group_id,
        text=f"⏰ *Reminder:* Time to *{habit}*! Stay on track 💪",
        reply_markup=create_done_keyboard(group_id, habit),
        parse_mode='Markdown'
    )

async def send_daily_summary(bot, group_id):
    group_ref = db.collection('groups').document(group_id)
    habits_ref = group_ref.collection("habits")
    today = get_today()

    habits = habits_ref.stream()
    completions_ref = group_ref.collection("completion_data").document(today)
    completions = completions_ref.get().to_dict() or {}

    msg = "🌟 *Daily Summary*\n\n"
    for habit in habits:
        done_users = completions.get(habit.id, [])
        progress = len(done_users) / 5
        progress_bar = get_progress_bar(min(progress, 1))
        msg += f"*{habit.to_dict()['habit_name']}*: {progress_bar} ({len(done_users)} completed)\n"

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

        for group_id in data["groups"]:
            # Reminders
            group_data = data["groups"][group_id]
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
