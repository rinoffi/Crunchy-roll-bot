🎌 Crunchyroll Telegram Downloader Bot

A Telegram bot that downloads anime directly from Crunchyroll using your premium account cookies.
Built with Python 3.11, yt-dlp, and python-telegram-bot — deployable via Docker.

   


---

✨ Features

🎥 Download premium Crunchyroll episodes

🔐 Secure cookie system (per user)

🧱 Easy Docker deployment

📜 Supports JSON / Netscape / Raw cookie formats

⚡ Fast downloads via yt-dlp

👑 Admin & Sudo user management



---

🧩 Prerequisites

Python 3.11+ (for manual setup)

Docker & Docker Compose (recommended)

Telegram Bot Token from @BotFather

Crunchyroll Premium Account (to access locked content)



---

🚀 Installation

🐳 Option 1: Docker (Recommended)

1. Clone the repository:

git clone <your-repo-url>
cd crunchyroll-telegram-bot


2. Create a .env file:

cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_USER_ID=your_telegram_user_id
EOF

> 💡 Get your user ID from @userinfobot




3. Build and run:

docker-compose up -d




---

🐍 Option 2: Manual Setup

1. Clone the repo:

git clone <your-repo-url>
cd crunchyroll-telegram-bot


2. Install dependencies:

pip install -r requirements.txt


3. Set environment variables:

export TELEGRAM_BOT_TOKEN=your_bot_token_here
export ADMIN_USER_ID=your_telegram_user_id


4. Run the bot:

python bot.py




---

🎫 Getting Your Crunchyroll Cookies

1. Install Cookie-Editor extension


2. Visit Crunchyroll and log in


3. Click the Cookie-Editor icon


4. Click Export → JSON


5. Copy the exported JSON data




---

💬 Bot Usage

1. Start the bot → /start


2. Set cookies → /setcookie (paste your JSON)


3. Send a Crunchyroll link to download



Example:

https://www.crunchyroll.com/watch/G14U41KE6/string-cranes-at-midday

The bot will download and send the video to you via Telegram 🎞️


---

⚙️ Commands

Command	Description

/start	Show welcome message
/help	Show usage info
/setcookie	Upload Crunchyroll cookies
/mysudo	Check your ID & authorization
/addsudo <id>	Add a sudo user (admin only)
/removesudo <id>	Remove a sudo user (admin only)
/listsudo	List all sudo users (admin only)



---

🧱 Configuration

🧾 Environment Variables

Variable	Description

TELEGRAM_BOT_TOKEN	Your Telegram bot token
ADMIN_USER_ID	Your Telegram user ID


📦 Docker Volumes

Path	Description

./downloads	Temporary downloads
./sudo_users.json	Persistent authorized users



---

👑 Authorization System

Role	Permissions

Admin	Full access
Sudo Users	Can use bot
Regular Users	Restricted


🛡️ Only Admin and Sudo users can download videos.


---

⚠️ Limitations

✅ No Telegram size limits (bot handles any quality)

⚡ Large files take longer to upload

🔁 Cookies reset when the bot restarts

💾 Sudo users persist via sudo_users.json



---

🩻 Troubleshooting

Issue	Cause	Solution

⚠️ “Please set your cookies first”	No cookies loaded	Use /setcookie and paste valid JSON
❌ “Video too large”	File > 50MB	Use lower quality or external hosting
🚫 “Unauthorized”	Not added as sudo	Ask admin to /addsudo <id>
🕒 “Download failed”	Cookie expired or invalid	Re-export and re-upload cookies



---

🔐 Security Notes

⚠️ Important:

Never share your cookie JSON file

Cookies contain your Crunchyroll session data

Each user's cookies are stored in memory only (not saved to disk)

sudo_users.json persists authorized users only



---

🤝 Contributing

Pull requests are welcome!
For major changes, open an issue before submitting PRs.


---

📜 License

MIT License
Feel free to use and modify with proper credit.


---

⚡ Credits

python-telegram-bot

yt-dlp

Crunchyroll

Maintained by ATX BOTZ
