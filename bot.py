import os
import asyncio
import logging
import time
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ChatType
import yt_dlp
import json

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store cookies per user
user_cookies = {}
# Store download info for quality selection
download_queue = {}
# Pending authorization requests
pending_auth = {}

# Admin and sudo users with expiry
ADMIN_ID = int(os.getenv('ADMIN_USER_ID', ''))
LOG_CHANNEL_ID = os.getenv('LOG_CHANNEL_ID', None)
sudo_users = {}  # {user_id: expiry_timestamp or None for permanent}
authorized_groups = set()

# Load data from files
def load_sudo_users():
    global sudo_users
    if os.path.exists('sudo_users.json'):
        try:
            with open('sudo_users.json', 'r') as f:
                data = json.load(f)
                sudo_users = {int(k): v for k, v in data.items()}
                logger.info(f"Loaded {len(sudo_users)} sudo users")
        except Exception as e:
            logger.error(f"Error loading sudo users: {e}")
            sudo_users = {}
    if ADMIN_ID:
        sudo_users[ADMIN_ID] = None  # Admin never expires

def save_sudo_users():
    try:
        with open('sudo_users.json', 'w') as f:
            json.dump(sudo_users, f)
    except Exception as e:
        logger.error(f"Error saving sudo users: {e}")

def load_authorized_groups():
    global authorized_groups
    if os.path.exists('authorized_groups.json'):
        try:
            with open('authorized_groups.json', 'r') as f:
                authorized_groups = set(json.load(f))
                logger.info(f"Loaded {len(authorized_groups)} authorized groups")
        except Exception as e:
            logger.error(f"Error loading groups: {e}")
            authorized_groups = set()

def save_authorized_groups():
    try:
        with open('authorized_groups.json', 'w') as f:
            json.dump(list(authorized_groups), f)
    except Exception as e:
        logger.error(f"Error saving groups: {e}")

def is_authorized(user_id: int) -> bool:
    """Check if user is admin or sudo user (and not expired)"""
    if user_id == ADMIN_ID:
        return True
    
    if user_id not in sudo_users:
        return False
    
    expiry = sudo_users[user_id]
    if expiry is None:  # Permanent access
        return True
    
    if time.time() > expiry:  # Expired
        del sudo_users[user_id]
        save_sudo_users()
        return False
    
    return True

def parse_time_duration(duration_str: str) -> int:
    """Parse time duration like '1d', '2w', '3m', '5h' to seconds"""
    duration_str = duration_str.lower().strip()
    
    # Extract number and unit
    match = re.match(r'(\d+)([hdwmy])', duration_str)
    if not match:
        return None
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    multipliers = {
        'h': 3600,           # hours
        'd': 86400,          # days
        'w': 604800,         # weeks
        'm': 2592000,        # months (30 days)
        'y': 31536000,       # years (365 days)
    }
    
    return amount * multipliers.get(unit, 0)

def format_time_remaining(expiry_timestamp):
    """Format remaining time in human readable format"""
    if expiry_timestamp is None:
        return "Permanent"
    
    remaining = expiry_timestamp - time.time()
    if remaining <= 0:
        return "Expired"
    
    days = int(remaining // 86400)
    hours = int((remaining % 86400) // 3600)
    
    if days > 0:
        return f"{days}d {hours}h"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{int(remaining // 60)}m"

async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Log message to log channel"""
    if LOG_CHANNEL_ID:
        try:
            await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error logging to channel: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # In groups, only admin can start
    if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if user_id != ADMIN_ID:
            return
        
        group_id = update.effective_chat.id
        if group_id not in authorized_groups:
            authorized_groups.add(group_id)
            save_authorized_groups()
            await update.message.reply_text(
                f"✅ Bot activated in this group!\n"
                f"Group ID: `{group_id}`\n"
                f"Authorized users can now use the bot here.",
                parse_mode='Markdown'
            )
            await log_to_channel(context, f"🔓 Bot activated in group: {update.effective_chat.title} ({group_id})")
        else:
            await update.message.reply_text("✅ Bot already active in this group!")
        return
    
    # In DM
    if not is_authorized(user_id):
        # Create authorization request
        pending_auth[user_id] = {
            'username': update.effective_user.username or 'No username',
            'first_name': update.effective_user.first_name,
            'timestamp': time.time()
        }
        
        # Notify admin
        if LOG_CHANNEL_ID:
            keyboard = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"auth_approve_{user_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"auth_deny_{user_id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=f"🔔 **New Authorization Request**\n\n"
                     f"User: {update.effective_user.first_name}\n"
                     f"Username: @{update.effective_user.username or 'None'}\n"
                     f"User ID: `{user_id}`\n\n"
                     f"Approve or deny access?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        await update.message.reply_text(
            "⏳ **Authorization Request Sent**\n\n"
            f"Your User ID: `{user_id}`\n"
            f"Username: @{update.effective_user.username or 'None'}\n\n"
            "Please wait for admin approval.\n"
            "You'll be notified once approved!",
            parse_mode='Markdown'
        )
        return
    
    welcome_message = """
🎌 **Crunchyroll Downloader Bot**

**Download Commands:**
`/rip <url>` - Download with quality selection
`/rip <url> -q 1080` - Direct 1080p
`/rip <url> -q 720` - Direct 720p
`/rip <url> --audio` - Audio only

**Batch Download:**
`/rip <url> -e 1-5` - Episodes 1 to 5
`/rip <url> -e 1,3,5` - Specific episodes

**Setup:**
/setcookie - Set Crunchyroll cookies
/mystatus - Check your access status

**Admin Commands:**
/addsudo <user_id> <time> - Add user with time limit
  Example: `/addsudo 123456 1m` (1 month)
  Example: `/addsudo 123456 permanent`
/removesudo <user_id> - Remove user
/listsudo - List all sudo users
/authgroup - Authorize group (use in group)

**Time formats:** h(hours), d(days), w(weeks), m(months), y(years)
Examples: 5h, 3d, 2w, 1m, 1y

Use /help for detailed commands!
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help information."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⚠️ You are not authorized.")
        return
    
    help_text = """
**📥 Download Commands:**

**Basic:**
`/rip <url>` - Interactive quality selection

**With Quality:**
`/rip <url> -q 1080` - 1080p
`/rip <url> -q 720` - 720p
`/rip <url> -q 480` - 480p

**Special:**
`/rip <url> --audio` - Audio only
`/rip <url> --all` - All qualities

**Batch Episodes:**
`/rip <series_url> -e 1-10` - Episodes 1-10
`/rip <series_url> -e 1,5,10` - Episodes 1,5,10

**Examples:**
`/rip https://crunchyroll.com/watch/G14U41 -q 1080`
`/rip https://crunchyroll.com/series/GY8V -e 1-5`

**Cookie Setup:**
1. Install Cookie-Editor (Firefox/Chrome)
2. Login to crunchyroll.com
3. Export cookies as JSON
4. Send to bot with /setcookie
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def set_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide user to set cookies."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⚠️ You are not authorized.")
        return
    
    await update.message.reply_text(
        "**How to get cookies (Firefox/Chrome):**\n\n"
        "**Firefox:**\n"
        "1. Install 'Cookie-Editor' extension\n"
        "2. Go to crunchyroll.com and login\n"
        "3. Click Cookie-Editor icon (🍪)\n"
        "4. Click 'Export' → Choose 'JSON'\n"
        "5. Paste the JSON here\n\n"
        "**Chrome:**\n"
        "Same steps as Firefox!\n\n"
        "⚠️ Make sure you have premium subscription!",
        parse_mode='Markdown'
    )

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a sudo user with time limit (admin only)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Admin only.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "**Usage:** `/addsudo <user_id> <time>`\n\n"
            "**Examples:**\n"
            "`/addsudo 123456 5h` - 5 hours\n"
            "`/addsudo 123456 3d` - 3 days\n"
            "`/addsudo 123456 2w` - 2 weeks\n"
            "`/addsudo 123456 1m` - 1 month\n"
            "`/addsudo 123456 1y` - 1 year\n"
            "`/addsudo 123456 permanent` - Permanent",
            parse_mode='Markdown'
        )
        return
    
    try:
        new_sudo_id = int(context.args[0])
        time_str = context.args[1].lower()
        
        if time_str == 'permanent':
            expiry = None
            expiry_text = "Permanent"
        else:
            duration = parse_time_duration(time_str)
            if duration is None:
                await update.message.reply_text("❌ Invalid time format. Use: 5h, 3d, 2w, 1m, 1y")
                return
            
            expiry = time.time() + duration
            expiry_text = format_time_remaining(expiry)
        
        sudo_users[new_sudo_id] = expiry
        save_sudo_users()
        
        # Notify the user
        try:
            await context.bot.send_message(
                chat_id=new_sudo_id,
                text=f"✅ **Access Granted!**\n\n"
                     f"You now have access to the bot!\n"
                     f"Duration: {expiry_text}\n\n"
                     f"Use /start to begin!",
                parse_mode='Markdown'
            )
        except:
            pass
        
        await update.message.reply_text(
            f"✅ User `{new_sudo_id}` added!\n"
            f"Duration: {expiry_text}",
            parse_mode='Markdown'
        )
        
        await log_to_channel(context, f"➕ Admin added sudo user: {new_sudo_id}\nDuration: {expiry_text}")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a sudo user (admin only)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Admin only.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/removesudo <user_id>`", parse_mode='Markdown')
        return
    
    try:
        sudo_id = int(context.args[0])
        if sudo_id == ADMIN_ID:
            await update.message.reply_text("❌ Cannot remove admin.")
            return
        
        if sudo_id in sudo_users:
            del sudo_users[sudo_id]
            save_sudo_users()
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=sudo_id,
                    text="⚠️ Your access to the bot has been revoked."
                )
            except:
                pass
            
            await update.message.reply_text(f"✅ User `{sudo_id}` removed!", parse_mode='Markdown')
            await log_to_channel(context, f"➖ Admin removed sudo user: {sudo_id}")
        else:
            await update.message.reply_text("❌ User is not a sudo user.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def list_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all sudo users (admin only)."""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Admin only.")
        return
    
    if not sudo_users:
        await update.message.reply_text("No sudo users configured.")
        return
    
    sudo_list = []
    for uid, expiry in sudo_users.items():
        remaining = format_time_remaining(expiry)
        role = "👑 Admin" if uid == ADMIN_ID else "🔐 Sudo"
        sudo_list.append(f"{role} `{uid}` - {remaining}")
    
    await update.message.reply_text(
        f"**Sudo Users ({len(sudo_users)}):**\n\n" + "\n".join(sudo_list),
        parse_mode='Markdown'
    )

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user's status."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "No username"
    
    if user_id == ADMIN_ID:
        role = "👑 Admin"
        status = "✅ Authorized (Permanent)"
    elif user_id in sudo_users:
        role = "🔐 Sudo User"
        expiry = sudo_users[user_id]
        remaining = format_time_remaining(expiry)
        status = f"✅ Authorized ({remaining} remaining)"
    else:
        role = "👤 Guest"
        status = "❌ Not Authorized"
    
    await update.message.reply_text(
        f"**Your Status:**\n\n"
        f"User ID: `{user_id}`\n"
        f"Username: @{username}\n"
        f"Role: {role}\n"
        f"Status: {status}",
        parse_mode='Markdown'
    )

async def auth_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Authorize a group (admin only, must be used in group)."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ Admin only.")
        return
    
    if chat_type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await update.message.reply_text("❌ This command must be used in a group!")
        return
    
    group_id = update.effective_chat.id
    group_name = update.effective_chat.title
    
    if group_id not in authorized_groups:
        authorized_groups.add(group_id)
        save_authorized_groups()
        await update.message.reply_text(
            f"✅ Group authorized!\n"
            f"Group: {group_name}\n"
            f"ID: `{group_id}`",
            parse_mode='Markdown'
        )
        await log_to_channel(context, f"🔓 Group authorized: {group_name} ({group_id})")
    else:
        await update.message.reply_text("✅ Group already authorized!")

async def auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle authorization approval/denial callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("⚠️ Admin only!", show_alert=True)
        return
    
    action, user_id = query.data.split('_')[1], int(query.data.split('_')[2])
    
    if user_id not in pending_auth:
        await query.edit_message_text("❌ Request expired or already processed.")
        return
    
    user_info = pending_auth[user_id]
    
    if action == 'approve':
        # Ask admin for duration
        await query.edit_message_text(
            f"✅ Approving user: {user_info['first_name']} ({user_id})\n\n"
            f"Send duration using:\n"
            f"`/addsudo {user_id} <time>`\n\n"
            f"Example: `/addsudo {user_id} 1m`",
            parse_mode='Markdown'
        )
        del pending_auth[user_id]
    else:
        # Deny
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Your authorization request was denied."
            )
        except:
            pass
        
        await query.edit_message_text(f"❌ Denied access for user: {user_info['first_name']} ({user_id})")
        del pending_auth[user_id]

async def rip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main download command."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # Check authorization
    if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        group_id = update.effective_chat.id
        if group_id not in authorized_groups:
            return
    
    if not is_authorized(user_id):
        await update.message.reply_text(f"⚠️ Not authorized.\nYour ID: `{user_id}`\nUse /start to request access.", parse_mode='Markdown')
        return
    
    if user_id not in user_cookies:
        await update.message.reply_text("⚠️ Set cookies first: /setcookie")
        return
    
    if not context.args:
        await update.message.reply_text(
            "**Usage:**\n"
            "`/rip <url>` - Interactive\n"
            "`/rip <url> -q 1080` - Direct\n\n"
            "Use /help for all options",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    args_str = ' '.join(context.args[1:])
    
    # Parse flags
    quality = None
    audio_only = '--audio' in args_str
    
    quality_match = re.search(r'-q\s+(\d+)|--quality\s+(\d+)', args_str)
    if quality_match:
        quality = quality_match.group(1) or quality_match.group(2)
    
    if not re.search(r'crunchyroll\.com', url):
        await update.message.reply_text("❌ Invalid Crunchyroll URL")
        return
    
    if quality or audio_only:
        await direct_download(update, context, url, user_id, quality, audio_only)
    else:
        await show_quality_options(update, context, url, user_id)

async def direct_download(update, context, url, user_id, quality, audio_only):
    """Direct download with specified quality."""
    status_msg = await update.message.reply_text("⏳ Starting download...")
    
    try:
        cookie_file = f"cookies_{user_id}.txt"
        await create_cookie_file(user_id, cookie_file)
        
        info = await fetch_video_info(url, cookie_file, status_msg)
        if not info:
            return
        
        filename = generate_filename(info)
        
        if audio_only:
            format_str = 'bestaudio/best'
            ext = 'mp3'
            quality_text = "Audio"
        else:
            format_str = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
            ext = 'mkv'
            quality_text = f"{quality}p"
        
        await download_and_upload(update, context, status_msg, url, cookie_file, format_str, ext, filename, quality_text, user_id)
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def show_quality_options(update, context, url, user_id):
    """Show quality selection buttons."""
    status_msg = await update.message.reply_text("⏳ Fetching qualities...")
    
    try:
        cookie_file = f"cookies_{user_id}.txt"
        await create_cookie_file(user_id, cookie_file)
        
        info = await fetch_video_info(url, cookie_file, status_msg)
        if not info:
            return
        
        formats = info.get('formats', [])
        video_formats = {}
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('height'):
                height = f.get('height')
                if height not in video_formats:
                    video_formats[height] = f.get('format_id')
        
        download_queue[user_id] = {
            'url': url,
            'info': info,
            'formats': video_formats,
            'cookie_file': cookie_file
        }
        
        keyboard = []
        for height in sorted(video_formats.keys(), reverse=True):
            quality_text = f"📺 {height}p"
            if height >= 1080:
                quality_text += " (Best)"
            keyboard.append([InlineKeyboardButton(quality_text, callback_data=f"q_{height}")])
        
        keyboard.append([InlineKeyboardButton("🎵 Audio Only", callback_data="q_audio")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        title = info.get('title', 'Unknown')
        series = info.get('series', 'Unknown Series')
        
        await status_msg.edit_text(
            f"**{series}**\n{title}\n\n📋 Select quality:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality button clicks."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id not in download_queue:
        await query.edit_message_text("❌ Session expired. Send /rip again.")
        return
    
    quality = query.data.replace("q_", "")
    queue_data = download_queue[user_id]
    
    await query.edit_message_text("⏳ Starting download...")
    
    try:
        url = queue_data['url']
        info = queue_data['info']
        cookie_file = queue_data['cookie_file']
        
        filename = generate_filename(info)
        
        if quality == "audio":
            format_str = 'bestaudio/best'
            ext = 'mp3'
            quality_text = "Audio"
        else:
            format_str = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
            ext = 'mkv'
            quality_text = f"{quality}p"
        
        await download_and_upload(query, context, query.message, url, cookie_file, format_str, ext, filename, quality_text, user_id)
        
        del download_queue[user_id]
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def create_cookie_file(user_id, cookie_file):
    """Create cookie file from stored cookies."""
    cookies = user_cookies[user_id]
    with open(cookie_file, 'w') as f:
        f.write("# Netscape HTTP Cookie File\n")
        if isinstance(cookies, list):
            for cookie in cookies:
                if isinstance(cookie, dict):
                    domain = cookie.get('domain', '.crunchyroll.com')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = cookie.get('path', '/')
                    secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                    expiration = str(int(cookie.get('expirationDate', 0)))
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")

async def fetch_video_info(url, cookie_file, status_msg):
    """Fetch video info with retry."""
    ydl_opts = {
        'cookiefile': cookie_file,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }
    
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            if '429' in str(e) and attempt < 2:
                await status_msg.edit_text(f"⏳ Rate limited, retry {attempt+1}/3...")
                time.sleep((attempt+1)*5)
            else:
                raise

def generate_filename(info):
    """Generate proper filename."""
    series = info.get('series', 'Unknown')
    season = info.get('season_number', 1)
    episode = info.get('episode_number', 1)
    title = info.get('episode', info.get('title', 'Unknown'))
    
    filename = f"{series} - S{season:02d}E{episode:02d} - {title}"
    return "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()

async def download_and_upload(source, context, status_msg, url, cookie_file, format_str, ext, filename, quality_text, user_id):
    """Download and upload file."""
    ydl_opts = {
        'cookiefile': cookie_file,
        'format': format_str,
        'merge_output_format': ext,
        'outtmpl': f'downloads/{filename}.%(ext)s',
        'socket_timeout': 30,
    }
    
    for attempt in range(3):
        try:
            await status_msg.edit_text(f"📥 Downloading {quality_text}...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            break
        except Exception as e:
            if '429' in str(e) and attempt < 2:
                time.sleep((attempt+1)*5)
            else:
                raise
    
    output_file = f"downloads/{filename}.{ext}"
    file_size_mb = os.path.getsize(output_file) / 1024 / 1024
    
    await status_msg.edit_text(f"📤 Uploading... ({file_size_mb:.2f} MB)")
    
    with open(output_file, 'rb') as video:
        if ext == 'mp3':
            await status_msg.reply_audio(
                audio=video,
                caption=f"🎵 {filename}",
                read_timeout=300,
                write_timeout=300
            )
        else:
            await status_msg.reply_video(
                video=video,
                caption=f"🎌 {filename}\n📺 {quality_text} | 📦 {file_size_mb:.2f} MB",
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300
            )
    
    os.remove(output_file)
    os.remove(cookie_file)
    await status_msg.delete()
    
    # Log to channel
    await log_to_channel(context, f"📥 Download: {filename}\nUser: {user_id}\nQuality: {quality_text}\nSize: {file_size_mb:.2f} MB")
    
    logger.info(f"User {user_id} downloaded: {filename} ({quality_text})")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (cookies or URLs)."""
    user_id = update.effective_user.id
    text = update.message.text
    chat_type = update.effective_chat.type
    
    # In groups, check if authorized
    if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        group_id = update.effective_chat.id
        if group_id not in authorized_groups:
            return
    
    if not is_authorized(user_id):
        return
    
    # Cookie data
    if text.startswith('[') or text.startswith('{'):
        try:
            cookies = json.loads(text)
            user_cookies[user_id] = cookies
            await update.message.reply_text("✅ Cookies saved!\n\nUse: `/rip <url>`", parse_mode='Markdown')
        except:
            await update.message.reply_text("❌ Invalid JSON format.")
        return
    
    # URL without /rip command
    if 'crunchyroll.com/watch' in text:
        await update.message.reply_text("Use: `/rip " + text + "`", parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads (cookie JSON files)."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # In groups, check if authorized
    if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        group_id = update.effective_chat.id
        if group_id not in authorized_groups:
            return
    
    if not is_authorized(user_id):
        await update.message.reply_text(f"⚠️ Not authorized.\nYour ID: `{user_id}`", parse_mode='Markdown')
        return
    
    document = update.message.document
    
    # Check if it's a JSON file
    if not document.file_name.endswith('.json'):
        await update.message.reply_text("⚠️ Please upload a .json file containing cookies.")
        return
    
    # Check file size (max 5MB for cookies)
    if document.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("❌ File too large. Cookie files should be small.")
        return
    
    status_msg = await update.message.reply_text("📥 Reading cookie file...")
    
    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_path = f"cookies_upload_{user_id}.json"
        await file.download_to_drive(file_path)
        
        # Read and parse JSON
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            cookies = json.loads(content)
        
        # Validate it's a cookie array
        if not isinstance(cookies, list):
            await status_msg.edit_text("❌ Invalid cookie format. Should be an array of cookies.")
            os.remove(file_path)
            return
        
        # Check if it has cookie-like objects
        if len(cookies) == 0:
            await status_msg.edit_text("❌ Empty cookie file!")
            os.remove(file_path)
            return
        
        # Save cookies
        user_cookies[user_id] = cookies
        
        # Cleanup
        os.remove(file_path)
        
        await status_msg.edit_text(
            f"✅ **Cookies loaded successfully!**\n\n"
            f"📊 Loaded {len(cookies)} cookies\n"
            f"📝 File: `{document.file_name}`\n\n"
            f"Now you can use: `/rip <url>`",
            parse_mode='Markdown'
        )
        
        await log_to_channel(context, f"🍪 User {user_id} uploaded cookie file: {document.file_name} ({len(cookies)} cookies)")
        
    except json.JSONDecodeError as e:
        await status_msg.edit_text(f"❌ Invalid JSON file. Please check the format.\n\nError: {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Error processing cookie file: {e}")
        await status_msg.edit_text(f"❌ Error reading file: {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    """Start the bot."""
    os.makedirs('downloads', exist_ok=True)
    load_sudo_users()
    load_authorized_groups()
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found")
        return
    
    if not ADMIN_ID:
        logger.error("ADMIN_USER_ID not found")
        return
    
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info(f"Sudo users: {len(sudo_users)}")
    logger.info(f"Authorized groups: {len(authorized_groups)}")
    if LOG_CHANNEL_ID:
        logger.info(f"Log channel: {LOG_CHANNEL_ID}")
    
    application = Application.builder().token(token).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setcookie", set_cookie))
    application.add_handler(CommandHandler("rip", rip_command))
    application.add_handler(CommandHandler("addsudo", add_sudo))
    application.add_handler(CommandHandler("removesudo", remove_sudo))
    application.add_handler(CommandHandler("listsudo", list_sudo))
    application.add_handler(CommandHandler("mystatus", my_status))
    application.add_handler(CommandHandler("authgroup", auth_group))
    application.add_handler(CallbackQueryHandler(quality_callback, pattern="^q_"))
    application.add_handler(CallbackQueryHandler(auth_callback, pattern="^auth_"))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
