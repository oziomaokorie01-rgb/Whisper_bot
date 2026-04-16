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

# Temperature set to 0.9 for more "human-like" and creative responses
model = genai.GenerativeModel(
    'gemini-1.5-flash',
    generation_config={"temperature": 0.9, "top_p": 0.95}
)
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
    instructions = (
        "💜 <b>THE WHISPER: HOW TO START</b> 💙\n\n"
        "1️⃣ <b>ACTIVATE:</b> Click the button below and hit 'START' in my private chat.\n"
        "2️⃣ <b>JOIN:</b> Come back here and type /join.\n"
        "3️⃣ <b>BEGIN:</b> Once 3+ victims are in, the host types /begin.\n\n"
        "<i>Architect: @Senseii_ciel</i>"
    )
    keyboard = [
        [InlineKeyboardButton("📩 1. ACTIVATE PRIVATE CHAT", url="https://t.me/The_whisperbot?start=join")],
        [InlineKeyboardButton("🐦 Follow the Architect", url="https://x.com/Senseii_ciel")]
    ]
    await update.message.reply_text(instructions, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

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
        
        btn = [[InlineKeyboardButton("📲 CLICK HERE & PRESS 'START'", url="https://t.me/The_whisperbot?start=join")]]
        await update.message.reply_text(
            f"✅ <b>{safe_name} joined!</b>\n\n"
            f"⚠️ <b>MANDATORY:</b> Click the button below and hit 'START' in our private chat or I cannot whisper your role!",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode='HTML'
        )

async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)
    
    # 1. Host Verification
    if game and update.effective_user.id != game['host_id']:
        await update.message.reply_text("Only the Architect's proxy (the host) can start this chaos.")
        return

    # 2. Player Count Check
    if not game or len(game['players']) < 3:
        current = len(game['players']) if game else 0
        await update.message.reply_text(f"❌ <b>FAILED:</b> I need 3 victims. (Current: {current}/3)", parse_mode='HTML')
        return

    try:
        # 3. DYNAMIC GOAL GENERATION (With Safety)
        themes = ["Paranoia/Trust", "Linguistic rules", "Absurdist humor", "Passive-aggressive drama"]
        selected_theme = random.choice(themes)
        prompt = f"Generate a chaotic 10-word social goal for a group chat based on the theme: {selected_theme}."
        
        # If Gemini is slow/down, this might be where it hangs
        res = model.generate_content(prompt)
        if not res or not res.text:
            game['goal'] = "Gaslight everyone into thinking the bot is broken."
        else:
            game['goal'] = html.escape(res.text.strip())
        
        # 4. Role Shuffling
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
        
        # 5. The Whispering (The Handshake Check)
        for pid, role in roles.items():
            pwr = {"Traitor 😈": "/gaslight", "Detective 🕵️": "/scan", "Guardian 🛡️": "/shield", "Chaos Agent 🎲": "/blackout"}.get(role, "Survival")
            try: 
                await context.bot.send_message(chat_id=pid, text=f"🔥 ROLE: {role}\nPOWER: {pwr}")
            except Exception as e:
                p_name = next((p['name'] for p in game['players'] if p['id'] == pid), "A player")
                await update.message.reply_text(f"❌ <b>FAILED:</b> {html.escape(p_name)} blocked my whisper! Hit 'START' in my DM and try again.", parse_mode='HTML')
                return

        game['active'] = True
        await update.message.reply_text(f"💜 <b>GOAL: {game['goal']}</b> 💙\nRoles whispered. The game is ON.", parse_mode='HTML')

    except Exception as e:
   
        await update.message.reply_text(f"⚠️ <b>ARCHITECT ERROR:</b> {str(e)}", parse_mode='HTML')

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
        # CONTEXT-AWARE ROASTING
        banter_prompt = (
            f"{SYSTEM_PROMPT}\n"
            f"The current goal is: {game['goal']}.\n"
            f"Player {user.first_name} said: '{text}'.\n"
            "If they are failing the goal or acting basic, roast them. Keep it under 15 words."
        )
        res = model.generate_content(banter_prompt)
        await update.message.reply_text(html.escape(res.text))

async def accuse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = games.get(update.effective_chat.id)
    if game and game['active'] and context.args:
        voter_id = update.effective_user.id
        if voter_id in game['votes']: return
        
        target = context.args[0].lower().replace("@", "")
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

    bulk_data = []
    for p in game['players']:
        pid = p['id']
        role = game['roles'].get(pid, "Witness 👤")
        pts = game['points'].get(pid, 0)
        report += f"• {html.escape(p['name'])}: {role} ({pts} pts)\n"
        
        col = role_map.get(role, "witness_pts")
        bulk_data.append({"user_id": pid, "username": p['name'], col: pts})

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

    try: supabase.table("leaderboard").upsert(bulk_data).execute()
    except: pass

    report += "\n\n— 🔗 Follow the Architect: <a href='https://x.com/Senseii_ciel'>@Senseii_ciel</a> —"
    await update.message.reply_text(report, parse_mode='HTML', disable_web_page_preview=True)
    
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
    
