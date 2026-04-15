import html
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
SYSTEM_PROMPT = "You are 'The Whisper', a chaotic Game Master created by @Senseii_ciel. Vibe: Electric Purple 💜 and Teal Blue 💙. Mock players and stir drama."

games = {}

# --- HELPERS ---
def get_game(uid, chat_id=None):
    if chat_id and chat_id in games:
        if any(p['id'] == uid for p in games[chat_id]['players']): return games[chat_id]
    for g_id, game in games.items():
        if any(p['id'] == uid for p in game['players']): return game
    return None

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🐦 Follow the Architect", url="https://x.com/Senseii_ciel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💜 <b>THE WHISPER</b> 💙\n"
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
            'points': {}, 'protected': [], 'blackout': False, 'votes': {},
            'host_id': user.id
        }
    
    game = games[chat_id]
    if not any(p['id'] == user.id for p in game['players']):
        game['players'].append({'id': user.id, 'name': user.first_name})
        game['points'][user.id] = 10
        safe_name = html.escape(user.first_name)
        btn = [[InlineKeyboardButton("📩 Activate My Whisper (Required)", url="https://t.me/The_whisperbot")]]
        await update.message.reply_text(
            f"✅ <b>{safe_name} joined!</b>\n\n"
            f"⚠️ <i>Attention Victims:</i> I cannot whisper your secret role unless you message me privately first!",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode='HTML'
        )

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    
    if game and update.effective_user.id != game['host_id']:
        await update.message.reply_text("Only the Architect's proxy (the host) can start this chaos.")
        return

    if not game or len(game['players']) < 3:
        await update.message.reply_text("I need 3 victims.")
        return

    res = model.generate_content("Generate a chaotic 10-word social goal for a group chat.")
    game['goal'] = html.escape(res.text.strip())
    
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
    
    for pid, role in roles.items():
        pwr = {"Traitor 😈": "/gaslight", "Detective 🕵️": "/scan", "Guardian 🛡️": "/shield", "Chaos Agent 🎲": "/blackout"}.get(role, "Survival")
        try: 
            await context.bot.send_message(chat_id=pid, text=f"Role: {role}\nPower: {pwr}")
        except:
            p_name = next((p['name'] for p in game['players'] if p['id'] == pid), "A player")
            await update.message.reply_text(f"❌ <b>FAILED:</b> {html.escape(p_name)} hasn't started a chat with me! DM me and try /begin again.", parse_mode='HTML')
            return

    game['active'] = True
    await update.message.reply_text(f"💜 <b>GOAL: {game['goal']}</b> 💙\nRoles whispered.", parse_mode='HTML')

# --- POWERS ---
async def gaslight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(update.effective_user.id, update.effective_chat.id)
    if game and "Traitor" in game['roles'].get(update.effective_user.id, ""):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="🚨 [SYSTEM ALERT]: Guardian failure detected. -5 pts.")

async def shield(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Who are you shielding? Use /shield name")
        return
        
    game = get_game(update.effective_user.id, update.effective_chat.id)
    if game and game['roles'].get(update.effective_user.id) == "Guardian 🛡️":
        target = html.escape(context.args[0].replace("@", ""))
        game['protected'].append(target)
        await update.message.reply_text(f"🛡️ Shield active on {target}.", parse_mode='HTML')

async def blackout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(update.effective_user.id, update.effective_chat.id)
    if game and game['roles'].get(update.effective_user.id) == "Chaos Agent 🎲":
        game['blackout'] = True
        await update.message.reply_text("🎲 <b>GLITCH DETECTED.</b> Going dark for 5 minutes...", parse_mode='HTML')
        
        async def end_blackout(g, c_id):
            await asyncio.sleep(300)
            g['blackout'] = False
            try: await context.bot.send_message(chat_id=c_id, text="💙 I'm watching again.")
            except: pass
        asyncio.create_task(end_blackout(game, update.effective_chat.id))

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_game(update.effective_user.id, update.effective_chat.id)
    if not game or not context.args: return
    
    if game['roles'].get(update.effective_user.id) == "Detective 🕵️":
        target = context.args[0].lower().replace("@", "")
        is_traitor = any(target == p['name'].lower() for p in game['players'] if "Traitor" in game['roles'].get(p['id'], ""))
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
        # TWEAK: Escaped AI response to prevent crash
        res = model.generate_content(f"{SYSTEM_PROMPT}\nGoal: {game['goal']}. {user.first_name} said: {text}.")
        await update.message.reply_text(html.escape(res.text))

async def accuse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id)
    if game and game['active'] and context.args:
        voter_id = update.effective_user.id
        if voter_id in game['votes']: return
        
        target = context.args[0].lower().replace("@", "")
        # Validate that the accused is actually in the game
        if any(target == p['name'].lower() for p in game['players']):
            game['votes'][voter_id] = target
            if len(game['votes']) >= (len(game['players']) // 2) + 1:
                await reveal(update, context)

async def reveal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    if not game: return

    report = "💜 <b>CHAOS REPORT</b> 💙\n\n"
    role_map = {
        "Traitor 😈": "traitor_pts", "Detective 🕵️": "detective_pts",
        "Guardian 🛡️": "guardian_pts", "Chaos Agent 🎲": "chaos_pts"
    }

    # FIX 4/7: Prep bulk data for Supabase
    bulk_data = []
    for p in game['players']:
        pid = p['id']
        role = game['roles'].get(pid, "Witness 👤")
        pts = game['points'].get(pid, 0)
        report += f"• {html.escape(p['name'])}: {role} ({pts} pts)\n"
        
        col = role_map.get(role, "witness_pts")
        bulk_data.append({"user_id": pid, "username": p['name'], col: pts})

        # Send individual DMs
        tweet_text = f"I survived 'The Whisper' as the {role} with {pts} points! 💜💙\n\nArchitect: @Senseii_ciel\n#TheWhisper #AI"
        tweet_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(tweet_text)}"
        tweet_btn = [[InlineKeyboardButton("🐦 Post to Twitter", url=tweet_url)]]

        try: 
            await context.bot.send_message(
                chat_id=pid, 
                text=f"🔥 <b>THE REVEAL</b>\n\nYour Role: {role}\nYour Score: {pts}",
                reply_markup=InlineKeyboardMarkup(tweet_btn),
                parse_mode='HTML'
            )
        except: pass

    # Execute bulk Supabase upsert
    try: supabase.table("leaderboard").upsert(bulk_data).execute()
    except: pass

    report += "\n\n— 🔗 Follow the Architect: <a href='https://x.com/Senseii_ciel'>@Senseii_ciel</a> —"
    await update.message.reply_text(report, parse_mode='HTML', disable_web_page_preview=True)
    
    # FIX 5: Full cleanup
    if chat_id in games:
        del games[chat_id]

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
    
