# /// script
# requires-python = ">=3.10"
# dependencies = ["python-telegram-bot>=21.0"]
# ///
"""a telegram - Telegram bot bridge for a"""
import sys, os, asyncio, subprocess as sp

TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'adata', 'git', 'login', 'telegram_token.txt')
ALLOWED_FILE = os.path.join(os.path.dirname(TOKEN_FILE), 'telegram_users.txt')

def _token():
    for p in [TOKEN_FILE, os.path.expanduser('~/.config/a/telegram_token.txt')]:
        if os.path.exists(p): return open(p).read().strip()
    return os.environ.get('A_TELEGRAM_TOKEN')

def _allowed():
    if os.path.exists(ALLOWED_FILE): return {int(x) for x in open(ALLOWED_FILE).read().split() if x.strip()}
    return None

def _a_cmd(text):
    try: r = sp.run(['a', 'send'] + text.split(), capture_output=True, text=True, timeout=120); return (r.stdout + r.stderr).strip() or '(no output)'
    except sp.TimeoutExpired: return '! timeout'
    except Exception as e: return f'! {e}'

async def _run_bot(token):
    from telegram import Update
    from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
    allowed = _allowed()

    async def handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if allowed and update.effective_user.id not in allowed:
            await update.message.reply_text('unauthorized'); return
        text = update.message.text
        if not text: return
        result = await asyncio.get_event_loop().run_in_executor(None, _a_cmd, text)
        for i in range(0, len(result), 4096):
            await update.message.reply_text(result[i:i+4096])

    async def cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(str(update.effective_user.id))

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler('id', cmd_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print(f'telegram bot started')
    await app.run_polling(drop_pending_updates=True)

def run():
    sub = sys.argv[2] if len(sys.argv) > 2 else None
    if sub == 'setup':
        t = input('Telegram bot token (@BotFather): ').strip()
        if not t: print('x no token'); return
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        open(TOKEN_FILE, 'w').write(t + '\n')
        uid = input('Your telegram user ID (send /id to bot, or blank to skip): ').strip()
        if uid: open(ALLOWED_FILE, 'w').write(uid + '\n')
        print(f'ok token saved to {TOKEN_FILE}')
        return
    token = _token()
    if not token: print('x no token. run: a telegram setup'); return
    asyncio.run(_run_bot(token))

if __name__ == '__main__': run()
