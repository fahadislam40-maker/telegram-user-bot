import os
import sqlite3
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"

# আপনার নিজের Telegram numeric User ID এখানে দিন
ADMIN_ID = 123456789

DB_FILE = "users.db"


# ============================================================
# DATABASE
# ============================================================

def db_connect():
    return sqlite3.connect(DB_FILE)


def init_database():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            blocked INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def save_or_update_user(user):
    conn = db_connect()
    cur = conn.cursor()

    current_time = now_utc()

    cur.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user.id,)
    )

    exists = cur.fetchone()

    if exists:
        cur.execute("""
            UPDATE users
            SET username = ?,
                first_name = ?,
                last_name = ?,
                last_seen = ?
            WHERE user_id = ?
        """, (
            user.username,
            user.first_name,
            user.last_name,
            current_time,
            user.id
        ))
    else:
        cur.execute("""
            INSERT INTO users
            (
                user_id,
                username,
                first_name,
                last_name,
                first_seen,
                last_seen,
                blocked
            )
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (
            user.id,
            user.username,
            user.first_name,
            user.last_name,
            current_time,
            current_time
        ))

    conn.commit()
    conn.close()


def is_blocked(user_id):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT blocked FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()

    conn.close()

    if not row:
        return False

    return row[0] == 1


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(user_id):
    return user_id == ADMIN_ID


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user:
        return

    save_or_update_user(user)

    if is_blocked(user.id):
        return

    await update.message.reply_text(
        "Welcome to XAUUSD FREE SIGNAL.\n\n"
        "You are registered successfully."
    )


# ============================================================
# NORMAL MESSAGE TRACKING
# ============================================================

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user:
        return

    save_or_update_user(user)

    if is_blocked(user.id):
        return


# ============================================================
# /STATS
# ============================================================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    conn = db_connect()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE blocked = 1"
    )
    blocked_users = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE blocked = 0"
    )
    active_users = cur.fetchone()[0]

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE last_seen >= ?
        AND blocked = 0
        """,
        (cutoff,)
    )

    monthly_users = cur.fetchone()[0]

    conn.close()

    await update.message.reply_text(
        "📊 BOT STATISTICS\n\n"
        f"👥 Total users: {total_users}\n"
        f"🟢 Active users: {active_users}\n"
        f"📅 Last 30 days: {monthly_users}\n"
        f"🚫 Blocked users: {blocked_users}\n"
    )


# ============================================================
# /USERS
# ============================================================

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            user_id,
            username,
            first_name,
            last_name,
            first_seen,
            last_seen,
            blocked
        FROM users
        ORDER BY last_seen DESC
    """)

    rows = cur.fetchall()

    conn.close()

    if not rows:
        await update.message.reply_text(
            "No users registered yet."
        )
        return

    # Telegram message size limit handling
    message = "👥 USER LIST\n\n"

    for row in rows:

        user_id = row[0]
        username = row[1]
        first_name = row[2] or ""
        last_name = row[3] or ""
        first_seen = row[4]
        last_seen = row[5]
        blocked = row[6]

        display_name = (
            f"{first_name} {last_name}".strip()
        )

        if not display_name:
            display_name = "No name"

        username_text = (
            f"@{username}"
            if username
            else "No username"
        )

        status = "🚫 BLOCKED" if blocked else "🟢 ACTIVE"

        entry = (
            f"ID: {user_id}\n"
            f"Name: {display_name}\n"
            f"Username: {username_text}\n"
            f"First: {first_seen[:19]}\n"
            f"Last: {last_seen[:19]}\n"
            f"Status: {status}\n"
            f"--------------------\n"
        )

        if len(message) + len(entry) > 3500:

            await update.message.reply_text(message)

            message = ""

        message += entry

    if message:
        await update.message.reply_text(message)


# ============================================================
# /USER ID
# ============================================================

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/user 123456789"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Invalid user ID."
        )
        return

    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            user_id,
            username,
            first_name,
            last_name,
            first_seen,
            last_seen,
            blocked
        FROM users
        WHERE user_id = ?
    """, (target_id,))

    row = cur.fetchone()

    conn.close()

    if not row:
        await update.message.reply_text(
            "User not found."
        )
        return

    username = (
        f"@{row[1]}"
        if row[1]
        else "No username"
    )

    status = "BLOCKED" if row[6] else "ACTIVE"

    await update.message.reply_text(
        "👤 USER INFORMATION\n\n"
        f"Telegram ID: {row[0]}\n"
        f"Name: {(row[2] or '')} {(row[3] or '')}\n"
        f"Username: {username}\n"
        f"First seen: {row[4]}\n"
        f"Last seen: {row[5]}\n"
        f"Status: {status}"
    )


# ============================================================
# /BLOCK
# ============================================================

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/block 123456789"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Invalid user ID."
        )
        return

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET blocked = 1 WHERE user_id = ?",
        (target_id,)
    )

    conn.commit()

    changed = cur.rowcount

    conn.close()

    if changed:
        await update.message.reply_text(
            f"🚫 User {target_id} blocked."
        )
    else:
        await update.message.reply_text(
            "User not found."
        )


# ============================================================
# /UNBLOCK
# ============================================================

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/unblock 123456789"
        )
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Invalid user ID."
        )
        return

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET blocked = 0 WHERE user_id = ?",
        (target_id,)
    )

    conn.commit()

    changed = cur.rowcount

    conn.close()

    if changed:
        await update.message.reply_text(
            f"🟢 User {target_id} unblocked."
        )
    else:
        await update.message.reply_text(
            "User not found."
        )


# ============================================================
# /BROADCAST
# ============================================================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/broadcast Your message here"
        )
        return

    broadcast_text = " ".join(context.args)

    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM users WHERE blocked = 0"
    )

    user_ids = [row[0] for row in cur.fetchall()]

    conn.close()

    sent = 0
    failed = 0

    await update.message.reply_text(
        f"📢 Broadcasting to {len(user_ids)} users..."
    )

    for target_id in user_ids:

        try:

            await context.bot.send_message(
                chat_id=target_id,
                text=broadcast_text
            )

            sent += 1

        except Exception:
            failed += 1

    await update.message.reply_text(
        "📢 BROADCAST COMPLETE\n\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )


# ============================================================
# ADMIN HELP
# ============================================================

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    await update.message.reply_text(
        "🛠 ADMIN COMMANDS\n\n"
        "/stats - Statistics\n"
        "/users - All users\n"
        "/user ID - User information\n"
        "/block ID - Block user\n"
        "/unblock ID - Unblock user\n"
        "/broadcast MESSAGE - Send message to all\n"
        "/admin - This menu"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("ERROR: Please put your Telegram Bot Token.")
        return

    init_database()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("stats", stats)
    )

    application.add_handler(
        CommandHandler("users", users)
    )

    application.add_handler(
        CommandHandler("user", user_info)
    )

    application.add_handler(
        CommandHandler("block", block_user)
    )

    application.add_handler(
        CommandHandler("unblock", unblock_user)
    )

    application.add_handler(
        CommandHandler("broadcast", broadcast)
    )

    application.add_handler(
        CommandHandler("admin", admin_help)
    )

    # Track normal messages
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            track_message
        )
    )

    print("====================================")
    print("XAUUSD FREE SIGNAL BOT")
    print("User tracking started")
    print("====================================")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
