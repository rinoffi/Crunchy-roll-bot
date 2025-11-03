import os
import asyncio
import logging
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# ==============================
# ✅ Basic Configuration
# ==============================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_cookies = {}  # store cookies in RAM

ADMIN_ID = int(os.getenv("ADMIN_USER_ID", "0"))
sudo_users = set()


# ==============================
# 🔐 Sudo Management
# ==============================
def load_sudo_users():
    global sudo_users
    if os.path.exists("sudo_users.json"):
        try:
            with open("sudo_users.json", "r") as f:
                sudo_users = set(json.load(f))
        except Exception as e:
            logger.error(f"Error loading sudo users: {e}")
    if ADMIN_ID:
        sudo_users.add(ADMIN_ID)


def save_sudo_users():
    try:
        with open("sudo_users.json", "w") as f:
            json.dump(list(sudo_users), f)
    except Exception as e:
        logger.error(f"Error saving sudo users: {e}")


def is_authorized(user_id: int) -> bool:
    return user_id == ADMIN_ID or user_id in sudo_users


# ==============================
# 🤖 Command Handlers
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⚠️ You are not authorized to use this bot.")
        return

    msg = """
🎌 **Crunchyroll Downloader Bot**

**Commands:**
/start - Show this message
/help - Help on using cookies
/setcookie - Set your Crunchyroll cookies
/clearcookie - Clear your saved cookies
/mysudo - Check your sudo status

**Admin:**
/addsudo <id>, /removesudo <id>, /listsudo

**Usage:**
1️⃣ Get your cookies using Cookie-Editor (Export JSON)  
2️⃣ Send /setcookie and paste the JSON  
3️⃣ Send a Crunchyroll URL to download
"""
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
**How to get Crunchyroll cookies (JSON):**
1. Install Cookie-Editor extension  
2. Login to https://www.crunchyroll.com  
3. Click Cookie-Editor → Export → JSON  
4. Copy full JSON text  
5. Send /setcookie and paste JSON directly here

After that, send any Crunchyroll video URL to download 🎥
"""
    await update.message.reply_text(text, parse_mode="Markdown")


# ==============================
# 🍪 Cookie Handling
# ==============================
async def set_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⚠️ You are not authorized to use this bot.")
        return

    await update.message.reply_text(
        "Please send your Crunchyroll cookies as JSON (from Cookie-Editor → Export → JSON).\n\n"
        "Example:\n```\n[\n  {\"domain\": \".crunchyroll.com\", \"name\": \"session_id\", \"value\": \"abc123\"}\n]\n```",
        parse_mode="Markdown"
    )


async def clear_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cookie_file = f"cookies_{user_id}.txt"
    if os.path.exists(cookie_file):
        os.remove(cookie_file)
    if user_id in user_cookies:
        del user_cookies[user_id]
    await update.message.reply_text("🧹 Cookies cleared successfully!")


# ==============================
# 👑 Sudo Commands
# ==============================
async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Only admin can add sudo users.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addsudo <user_id>")
        return

    try:
        new_id = int(context.args[0])
        sudo_users.add(new_id)
        save_sudo_users()
        await update.message.reply_text(f"✅ Added sudo user {new_id}")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID")


async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Only admin can remove sudo users.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removesudo <user_id>")
        return

    try:
        rm_id = int(context.args[0])
        if rm_id in sudo_users:
            sudo_users.remove(rm_id)
            save_sudo_users()
            await update.message.reply_text(f"🗑 Removed sudo user {rm_id}")
        else:
            await update.message.reply_text("❌ Not in sudo list.")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID")


async def list_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can view sudo list.")
        return

    if not sudo_users:
        await update.message.reply_text("No sudo users.")
        return

    msg = "\n".join([f"• {uid}" for uid in sudo_users])
    await update.message.reply_text(f"**Sudo Users:**\n{msg}", parse_mode="Markdown")


async def my_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = "👑 Admin" if user_id == ADMIN_ID else ("🔐 Sudo" if user_id in sudo_users else "👤 User")
    await update.message.reply_text(f"User ID: `{user_id}`\nRole: {role}", parse_mode="Markdown")


# ==============================
# 🧠 Message Handler
# ==============================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not is_authorized(user_id):
        await update.message.reply_text("⚠️ Unauthorized. Contact admin.")
        return

    # --- Check for cookie JSON ---
    if text.startswith("{") or text.startswith("["):
        try:
            cookies = json.loads(text)
            user_cookies[user_id] = cookies
            await update.message.reply_text("✅ Cookies saved successfully!")
        except Exception as e:
            await update.message.reply_text(f"❌ Invalid JSON: {e}")
        return

    # --- Crunchyroll URL ---
    if "crunchyroll.com" in text:
        if user_id not in user_cookies:
            await update.message.reply_text("⚠️ Set your cookies first using /setcookie")
            return
        await download_video(update, text, user_id)
        return

    await update.message.reply_text("Send a Crunchyroll link or /help.")


# ==============================
# 📥 Download Function
# ==============================
async def download_video(update: Update, url: str, user_id: int):
    status = await update.message.reply_text("⏳ Starting download...")

    try:
        cookie_file = f"cookies_{user_id}.txt"
        cookies = user_cookies[user_id]

        # Write Netscape cookie format
        with open(cookie_file, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get("domain", ".crunchyroll.com")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure", False) else "FALSE"
                exp = int(c.get("expirationDate", 0))
                name = c.get("name", "")
                value = c.get("value", "")
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{exp}\t{name}\t{value}\n")

        ydl_opts = {
            "cookiefile": cookie_file,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mkv",
            "outtmpl": f"downloads/%(title)s.%(ext)s",
            "quiet": False,
            "no_warnings": False
        }

        await status.edit_text("📥 Downloading video... please wait")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            title = info.get("title", "video")

        size_mb = os.path.getsize(filename) / 1024 / 1024
        await status.edit_text(f"📤 Uploading to Telegram...\nSize: {size_mb:.2f} MB")

        with open(filename, "rb") as vid:
            await update.message.reply_video(
                video=vid,
                caption=f"🎌 {title}\n📦 {size_mb:.2f} MB",
                supports_streaming=True
            )

        await status.delete()
        os.remove(filename)
        os.remove(cookie_file)
        logger.info(f"{user_id} downloaded {title}")

    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
        logger.error(f"Download error: {e}")
        if os.path.exists(cookie_file):
            os.remove(cookie_file)


# ==============================
# 🚀 Main
# ==============================
def main():
    os.makedirs("downloads", exist_ok=True)
    load_sudo_users()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not ADMIN_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN or ADMIN_USER_ID missing in environment.")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setcookie", set_cookie))
    app.add_handler(CommandHandler("clearcookie", clear_cookie))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("removesudo", remove_sudo))
    app.add_handler(CommandHandler("listsudo", list_sudo))
    app.add_handler(CommandHandler("mysudo", my_sudo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
