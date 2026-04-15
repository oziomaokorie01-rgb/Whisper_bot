
import os, random, asyncio, urllib.parse
import google.generativeai as genai
from dotenv import load_dotenv
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
genai.configure(api_key=os.getenv("GEMINI_KEY"))
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

model = genai.GenerativeModel('gemini-1.5-flash')
# Integrated Twitter handle into the AI personality
SYSTEM_PROMPT = "You are 'The Whisper', a chaotic Game Master created by @Senseii_ciel. Vibe: Electric Purple 💜 and Teal Blue 💙. Mock players and stir drama."

games = {}

# --- HELPERS ---
def get_game(uid):
    for g_id, game in games.items():
        if any(p['id'] == uid for p in game['players']): return game
    return None

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🐦 Follow the Architect", url="https://x.com/Senseii_ciel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💜 **THE WHISPER** 💙\n"
        "A game of social deduction and chaotic AI snark.\n\n"
        "Architect: @Senseii_ciel\n\n"
        "Type /join to enter the circle.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in games:
        games[chat_id] = {
            'players': [], 'roles': {}, 'active': False, 'goal': "", 
            'points': {}, 'protected': [], 'blackout': False, 'votes': {}
        }
    
    game = games[chat_id]
    if not any(p['id'] == user.id for p in game['players']):
        game['players'].append({'id': user.id, 'name': user.first_name})
        game['points'][user.id] = 10
        
        # Urges people to text the bot so it can DM their roles
        btn = [[InlineKeyboardButton("📩 Activate My Whisper (Required)", url="https://t.me/The_whisperbot")]]
        await update.message.reply_text(
            f"✅ **{user.first_name} joined!**\n\n"
            f"⚠️ *Attention Victims:* I cannot whisper your secret role unless you message me privately first!",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode='HTML'
        )

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game or len(game['players']) < 3:
        await update.message.reply_text("I need 3 victims.")
        return

    res = model.generate_content("Generate a chaotic 10-word social goal for a group chat.")
    game['goal'] = res.text.strip()
    
    p_ids = [p['id'] for p in game['players']]
    random.shuffle(p_ids)
    
    roles = {}
    roles[p_ids[0]] = "Traitor 😈"
    if len(p_ids) >= 8: roles[p_ids[1]] = "Traitor 😈"
    
    specialists = {2: "Detective 🕵️", 3: "Guardian 🛡️", 4: "Chaos Agent 🎲"}
    for i, name in specialists.items():
        if i < len(p_ids) and p_ids[i] not in roles: roles[p_ids[i]] = name
        
    for pid in p_ids:
        if pid not in roles: roles[pid] = "Witness 👤"
        
    game['roles'] = roles
    game['active'] = True
    await update.message.reply_text(f"💜 **GOAL: {game['goal']}** 💙\nRoles whispered.")

    for pid, role in roles.items():
        pwr = {"Traitor 😈": "/gaslight", "Detective 🕵️": "/scan", "Guardian 🛡️": "/shield", "Chaos Agent 🎲": "/blackout"}.get(role, "Survival")
        try: await context.bot.send_message(chat_id=pid, text=f"Role: {role}\nPower: {pwr}")
        except: pass

# --- POWERS ---
async def gaslight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(update.effective_user.id)
    if game and "Traitor" in game['roles'].get(update.effective_user.id, ""):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🚨 [SYSTEM ALERT]: Guardian failure detected. -5 pts.")

async def shield(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(update.effective_user.id)
    if game and game['roles'].get(update.effective_user.id) == "Guardian 🛡️" and context.args:
        target = context.args[0].replace("@", "")
        game['protected'].append(target)
        await update.message.reply_text(f"🛡️ Shield active on {target}.")

async def blackout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(update.effective_user.id)
    if game and game['roles'].get(update.effective_user.id) == "Chaos Agent 🎲":
        game['blackout'] = True
        await update.message.reply_text("🎲 **GLITCH DETECTED.** Going dark for 5 minutes...")
        await asyncio.sleep(300)
        game['blackout'] = False
        await update.message.reply_text("💙 I'm watching again.")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(update.effective_user.id)
    if game and game['roles'].get(update.effective_user.id) == "Detective 🕵️" and context.args:
        target = context.args[0].lower()
        # FIX: Correctly checking the players list using the game roles
        is_traitor = any(target in p['name'].lower() for p in game['players'] if "Traitor" in game['roles'].get(p['id'], ""))
        await update.message.reply_text("🔍 Suspect found." if is_traitor else "🔍 Likely clean.")

# --- ENGINE & ENDGAME ---
async def handle_banter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id)
    if not game or not game['active'] or game['blackout']: return

    user = update.effective_user
    text = update.message.text.lower()
    
    if any(w in text for w in ["sorry", "messed up", "oops"]) and user.first_name not in game['protected']:
        game['points'][user.id] -= 5
        for pid, r in game['roles'].items():
            if "Traitor" in r: game['points'][pid] += 5

    if random.random() < 0.15:
        res = model.generate_content(f"{SYSTEM_PROMPT}\nGoal: {game['goal']}. {user.first_name} said: {text}.")
        await update.message.reply_text(res.text)

async def accuse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id)
    if game and game['active'] and context.args:
        game['votes'][update.effective_user.id] = context.args[0]
        if len(game['votes']) >= (len(game['players']) // 2) + 1:
            await reveal(update, context)

async def reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game: return

    report = "💜 **CHAOS REPORT** 💙\n\n"
    role_map = {
        "Traitor 😈": "traitor_pts", "Detective 🕵️": "detective_pts",
        "Guardian 🛡️": "guardian_pts", "Chaos Agent 🎲": "chaos_pts"
    }

    for p in game['players']:
        pid = p['id']
        role = game['roles'].get(pid, "Witness 👤")
        pts = game['points'].get(pid, 0)
        report += f"• {p['name']}: {role} ({pts} pts)\n"
        
        try:
            col = role_map.get(role, "witness_pts")
            supabase.table("leaderboard").upsert({"user_id": pid, "username": p['name'], col: pts}).execute()
        except: pass

        # --- TWEET INTENT LOGIC ---
        tweet_text = f"I survived 'The Whisper' as the {role} with {pts} points! 💜💙\n\nArchitect: @Senseii_ciel\n#TheWhisper #AI"
        encoded_text = urllib.parse.quote(tweet_text)
        tweet_url = f"https://twitter.com/intent/tweet?text={encoded_text}"
        tweet_btn = [[InlineKeyboardButton("🐦 Post to Twitter", url=tweet_url)]]

        try: 
            await context.bot.send_message(
                chat_id=pid, 
                text=f"🔥 **THE REVEAL**\n\nYour Role: {role}\nYour Score: {pts}\n\nBrag about it on the timeline:",
                reply_markup=InlineKeyboardMarkup(tweet_btn),
                parse_mode='HTML'
            )
        except: pass

    # Twitter Footer for Group Chat
    report += "\n\n— 🔗 Follow the Architect: [x.com/Senseii_ciel](https://x.com/Senseii_ciel) —"
    await update.message.reply_text(report, parse_mode='HTML', disable_web_page_preview=True)
    game['active'] = False

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    cmds = [
        ("start", start), ("join", join), ("begin", begin), ("gaslight", gaslight), 
        ("shield", shield), ("blackout", blackout), ("scan", scan), ("accuse", accuse)
    ]
    for name, func in cmds: app.add_handler(CommandHandler(name, func))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_banter))
    print("The Whisper is alive.")
    app.run_polling()
