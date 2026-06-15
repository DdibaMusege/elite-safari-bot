from flask import Flask, request, jsonify, render_template_string
import requests
import os
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from langdetect import detect, LangDetectException
from openai import OpenAI

app = Flask(__name__)

# ========== CONFIG ==========
VERIFY_TOKEN = "safari_ug_2026"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# FIX: Initialize OpenAI client safely - check for None and handle errors
client_ai = None
if OPENAI_API_KEY:
    try:
        # Initialize OpenAI with just the API key, no extra parameters
        client_ai = OpenAI(api_key=OPENAI_API_KEY)
        print("✅ OpenAI client initialized successfully")
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize OpenAI client: {e}")
        print(f"   Error type: {type(e).__name__}")
        client_ai = None
else:
    print("⚠️  WARNING: OPENAI_API_KEY not set. Image generation will be disabled.")
    print("   To enable AI image generation, set OPENAI_API_KEY environment variable.")

PAYSTACK_LINKS = {
    "gorilla": "https://paystack.com/pay/safari-gorilla-183k",
    "murchison": "https://paystack.com/pay/safari-murchison-110k",
    "queen": "https://paystack.com/pay/safari-queen-146k",
    "custom": "https://paystack.com/pay/safari-custom-365k"
}

BUSINESSES = {
    "SAFARI_UG_001": {
        "name": "Elite Safari Bot by Snag.Ai",
        "admin_phone": "+256XXXXXXXXX",
        "packages": {
            "gorilla trekking 3d2n": {"price": 4380000, "usd": 1200, "deposit": 183000},
            "murchison falls 2d1n": {"price": 1642500, "usd": 450, "deposit": 110000},
            "queen elizabeth 3d2n": {"price": 2372500, "usd": 650, "deposit": 146000},
            "custom 7 day": {"price": 10220000, "usd": 2800, "deposit": 365000}
        }
    }
}

# Google Sheets
sheet = None
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    # FIX: Use worksheet() method instead of sheet1
    sheet = client.open("Elite_Safari_DB").worksheet(0)
    print("✅ Google Sheets connected successfully")
except FileNotFoundError:
    print("⚠️  WARNING: credentials.json not found. Google Sheets integration disabled.")
except Exception as e:
    print(f"❌ ERROR: Failed to connect to Google Sheets: {e}")

# ========== AI IMAGE GENERATOR ==========
def generate_safari_image(prompt, phone):
    if not client_ai:
        print("⚠️  Image generation disabled - OpenAI client not initialized")
        send_message(phone, "Image generation is not available. Please try again later.")
        return
    
    try:
        print(f"🖼️  Generating image with prompt: {prompt}")
        response = client_ai.images.generate(
            model="dall-e-3",
            prompt=f"{prompt}, Uganda safari, professional tourism photo, watermark 'SAMPLE ONLY'",
            size="1024x1024",
            quality="standard",
            n=1
        )
        image_url = response.data[0].url
        print(f"✅ Image generated successfully: {image_url}")
        send_image(phone, image_url, "Sample photo. Actual lodge may vary.")
        if sheet:
            sheet.append_row([datetime.now().isoformat(), phone, 'ai_image_request', prompt])
    except Exception as e:
        print(f"❌ ERROR generating image: {e}")
        send_message(phone, "Sorry, couldn't generate image. Please try again later.")

# ========== ADMIN DASHBOARD ==========
@app.route('/admin', methods=['GET'])
def admin_dashboard():
    if not sheet:
        return "Google Sheets not configured", 503
    
    try:
        records = sheet.get_all_records()
        html = """
        <html><head><title>Elite Safari Bot Admin</title>
        <style>body{font-family:Arial;padding:20px} table{border-collapse:collapse;width:100%}
        th,td{border:1px solid #ddd;padding:8px;text-align:left} th{background:#FF6B35;color:white}</style>
        </head><body>
        <h2>Elite Safari Bot - Live Dashboard</h2>
        <p>Total Leads: {{ total }} | Paid: {{ paid }} | Trips This Week: {{ trips }}</p>
        <table><tr><th>Phone</th><th>Trip</th><th>Dates</th><th>Pax</th><th>Status</th><th>Payment</th></tr>
        {% for r in records %}
        <tr><td>{{ r.phone }}</td><td>{{ r.trip_type }}</td><td>{{ r.dates }}</td><td>{{ r.pax }}</td><td>{{ r.trip_status }}</td><td>{{ r.payment_status }}</td></tr>
        {% endfor %}</table></body></html>
        """
        paid = len([r for r in records if r.get('payment_status') == 'PAID'])
        trips = len([r for r in records if r.get('trip_status') == 'Confirmed'])
        return render_template_string(html, records=records, total=len(records), paid=paid, trips=trips)
    except Exception as e:
        print(f"ERROR in admin_dashboard: {e}")
        return "Error loading dashboard", 500

# ========== HEALTH CHECK ==========
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway"""
    status = {
        "status": "healthy",
        "whatsapp_configured": bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID),
        "openai_configured": bool(client_ai is not None),
        "google_sheets_configured": bool(sheet is not None),
        "timestamp": datetime.now().isoformat()
    }
    return jsonify(status), 200

# ========== WEBHOOK ==========
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return 'Invalid token', 403

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if data and 'entry' in data and len(data['entry']) > 0:
            if 'changes' in data['entry'][0] and len(data['entry'][0]['changes']) > 0:
                if 'value' in data['entry'][0]['changes'][0]:
                    value = data['entry'][0]['changes'][0]['value']
                    if 'messages' in value and len(value['messages']) > 0:
                        msg = value['messages'][0]
                        phone = msg.get('from')
                        
                        # FIX 3: Validate phone exists before proceeding
                        if not phone:
                            print("ERROR: No phone number in webhook")
                            return 'OK', 200
                        
                        text = msg.get('text', {}).get('body', '').lower().strip() if isinstance(msg.get('text'), dict) else ''
                        
                        # FIX: Better language detection with error handling
                        lang = 'en'
                        if len(text) > 3:
                            try:
                                lang = detect(text)
                            except LangDetectException:
                                lang = 'en'

                        if text and phone:
                            handle_message(phone, text, lang)
                        if msg.get('type') == 'image' and 'image' in msg:
                            save_document(phone, msg['image'].get('id'), 'passport')
    except Exception as e:
        print(f"ERROR in webhook: {e}")
    return 'OK', 200

# ========== SAFARI FLOWS ==========
def handle_message(phone, text, lang):
    # FIX: Validate phone number format
    if not phone or not isinstance(phone, str):
        print(f"ERROR: Invalid phone number: {phone}")
        return
    
    user_state = get_user_state(phone)

    if text in ['hi', 'hello', 'start', 'safari']:
        send_message(phone, """Elite Safari Bot: Karibu Uganda! 🦁

I plan gorilla trekking, Murchison Falls, Queen Elizabeth safaris.

Choose your trip:
1. Gorilla trekking Bwindi/Mgahinga - $1,200/pax
2. Murchison Falls 2D/1N - $450/pax
3. Queen Elizabeth 3D/2N - $650/pax
4. Custom 7 Day Safari - $2,800/pax

Reply 1, 2, 3, or 4""")
        set_user_state(phone, 'awaiting_trip')

    elif user_state == 'awaiting_trip' and text == '1':
        set_user_state(phone, 'gorilla_dates')
        send_message(phone, """Gorilla trekking 🦍 - Best experience in Africa!

Send me:
1. Travel dates
2. Number of people
3. Passport photos for permit booking

Permits sell out 3 months early. Reply DONE when sent.""")

    elif user_state == 'awaiting_trip' and text == '2':
        set_user_state(phone, 'murchison_dates')
        send_message(phone, """Murchison Falls Safari 2D/1N 🦒

Send dates and number of people.
Includes: Game drive, boat cruise, accommodation, guide.
Reply DONE when sent.""")

    # FIX 4: Added missing handlers for options 3 and 4
    elif user_state == 'awaiting_trip' and text == '3':
        set_user_state(phone, 'queen_dates')
        send_message(phone, """Queen Elizabeth 3D/2N 🦓

Send dates and number of people.
Includes: Game drive, boat cruise, accommodation, guide.
Reply DONE when sent.""")

    elif user_state == 'awaiting_trip' and text == '4':
        set_user_state(phone, 'custom_dates')
        send_message(phone, """Custom 7 Day Safari 🦁

Send me:
1. Travel dates
2. Number of people
3. Your interests (wildlife, hiking, culture, etc)

We'll customize your perfect safari! Reply DONE when sent.""")

    # FIX 5: Made condition more specific to avoid false triggers
    elif 'show me' in text and ('gorilla' in text or 'bwindi' in text or 'lodge' in text or 'lion' in text):
        if 'gorilla' in text or 'bwindi' in text:
            generate_safari_image("Bwindi Impenetrable Forest gorilla trekking Uganda", phone)
        elif 'lodge' in text:
            generate_safari_image("Luxury safari lodge Uganda savannah", phone)
        elif 'lion' in text:
            generate_safari_image("Lion in Queen Elizabeth National Park Uganda", phone)

    elif text == 'done':
        if user_state == 'gorilla_dates':
            send_message(phone, f"""Gorilla trip details saved ✅

Package: $1,200 per person
Deposit: $50 USD / 183,000 UGX holds permits today
Balance: Due 30 days before trip

Pay deposit: {PAYSTACK_LINKS['gorilla']}
Reply PAID after payment.""")
            set_user_state(phone, 'awaiting_payment_gorilla')

        elif user_state == 'murchison_dates':
            send_message(phone, f"""Murchison trip saved ✅

Package: $450 per person
Deposit: $30 USD / 110,000 UGX confirms booking

Pay deposit: {PAYSTACK_LINKS['murchison']}
Reply PAID after payment.""")
            set_user_state(phone, 'awaiting_payment_murchison')

        elif user_state == 'queen_dates':
            send_message(phone, f"""Queen Elizabeth trip saved ✅

Package: $650 per person
Deposit: $40 USD / 146,000 UGX confirms booking

Pay deposit: {PAYSTACK_LINKS['queen']}
Reply PAID after payment.""")
            set_user_state(phone, 'awaiting_payment_queen')

        elif user_state == 'custom_dates':
            send_message(phone, f"""Custom safari details saved ✅

Package: $2,800 per person (7 days)
Deposit: $100 USD / 365,000 UGX confirms booking

Pay deposit: {PAYSTACK_LINKS['custom']}
Reply PAID after payment.""")
            set_user_state(phone, 'awaiting_payment_custom')

    elif text == 'paid':
        if user_state and 'gorilla' in user_state:
            update_sheet(phone, 'payment_status', 'PAID', 'gorilla trekking 3d2n')
            update_sheet(phone, 'trip_status', 'Confirmed')
            send_message(phone, """Payment confirmed ✅ 183,000 UGX

Permits booked! PDF confirmation in 24hrs.
WhatsApp group created with your guide.
He contacts you 3 days before trip.

Reply CONFIRM when packed. Karibu Uganda!""")
            notify_admin(f"GORILLA BOOKING PAID: {phone}")

        elif user_state and 'murchison' in user_state:
            update_sheet(phone, 'payment_status', 'PAID', 'murchison falls 2d1n')
            update_sheet(phone, 'trip_status', 'Confirmed')
            send_message(phone, """Payment confirmed ✅ 110,000 UGX

Safari confirmed! Guide contacts you 2 days before.
Pickup: Entebbe/Kampala 6:00 AM""")

        elif user_state and 'queen' in user_state:
            update_sheet(phone, 'payment_status', 'PAID', 'queen elizabeth 3d2n')
            update_sheet(phone, 'trip_status', 'Confirmed')
            send_message(phone, """Payment confirmed ✅ 146,000 UGX

Safari confirmed! Guide contacts you 2 days before.
Pickup: Entebbe/Kampala 6:00 AM""")

        elif user_state and 'custom' in user_state:
            update_sheet(phone, 'payment_status', 'PAID', 'custom 7 day')
            update_sheet(phone, 'trip_status', 'Confirmed')
            send_message(phone, """Payment confirmed ✅ 365,000 UGX

Custom safari confirmed! Our team will contact you within 24hrs to finalize details.
Guide contacts you 5 days before trip.

Karibu Uganda!""")

    elif text == 'confirm':
        update_sheet(phone, 'trip_status', 'Confirmed')
        send_message(phone, "Confirmed ✅ Guide will meet you at pickup point. Safe travels!")

# ========== TRIP REMINDER CRON ==========
@app.route('/cron/reminders', methods=['GET'])
def send_reminders():
    if not sheet:
        return "Google Sheets not configured", 503
    
    today = datetime.now().date()
    try:
        for row in sheet.get_all_records():
            if row.get('dates'):
                try:
                    # FIX 6: Better date parsing with safety checks
                    dates_str = row.get('dates', '')
                    if not dates_str:
                        continue
                    date_parts = dates_str.split(',')
                    if len(date_parts) == 0:
                        continue
                    trip_date = datetime.strptime(date_parts[0].strip(), '%Y-%m-%d').date()
                    days_left = (trip_date - today).days
                    if days_left in [7, 3, 1]:
                        msg = f"Reminder: {row['trip_type']} in {days_left} day(s) on {trip_date}. Pickup: Entebbe 6:00 AM. Bring passport."
                        send_message(row['phone'], msg)
                except (ValueError, IndexError, KeyError) as e:
                    print(f"Could not parse date: {row.get('dates', 'N/A')} - {e}")
    except Exception as e:
        print(f"ERROR in send_reminders: {e}")
    return 'Reminders sent', 200

# ========== PAYSTACK WEBHOOK ==========
@app.route('/paystack/webhook', methods=['POST'])
def paystack_webhook():
    try:
        data = request.json
        if data and data.get('event') == 'charge.success':
            phone = data.get('data', {}).get('metadata', {}).get('phone')
            if phone:
                update_sheet(phone, 'payment_status', 'PAID')
                send_message(phone, "Payment confirmed ✅ Trip confirmed. Check WhatsApp for guide contact.")
            else:
                print("ERROR: Missing phone in paystack webhook")
    except Exception as e:
        print(f"ERROR in paystack_webhook: {e}")
    return jsonify({'status': 'success'})

# ========== HELPERS ==========
def send_message(phone, message):
    # FIX 7: Validate environment variables before API call
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print(f"ERROR: WhatsApp credentials not configured")
        return
    
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        response = requests.post(url, headers=headers, json={"messaging_product": "whatsapp", "to": phone, "text": {"body": message}}, timeout=10)
        if response.status_code != 200:
            print(f"ERROR: WhatsApp API returned {response.status_code}: {response.text}")
    except Exception as e:
        print(f"ERROR sending message to {phone}: {e}")

def send_image(phone, image_url, caption):
    # FIX 7: Validate environment variables before API call
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print(f"ERROR: WhatsApp credentials not configured")
        return
    
    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        data = {"messaging_product": "whatsapp", "to": phone, "type": "image", "image": {"link": image_url, "caption": caption}}
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code != 200:
            print(f"ERROR: WhatsApp image API returned {response.status_code}: {response.text}")
    except Exception as e:
        print(f"ERROR sending image to {phone}: {e}")

def notify_admin(message):
    try:
        admin = BUSINESSES["SAFARI_UG_001"]["admin_phone"]
        send_message(admin, f"🚨 SAFARI ALERT: {message}")
    except Exception as e:
        print(f"ERROR notifying admin: {e}")

def save_document(phone, media_id, doc_type):
    try:
        if sheet and phone and media_id:
            sheet.append_row([datetime.now().isoformat(), phone, doc_type, media_id, get_user_state(phone)])
    except Exception as e:
        print(f"ERROR saving document: {e}")

# FIX: Better sheet lookup - find all matches by phone
def find_user_row(phone):
    if not sheet or not phone:
        return None
    try:
        # Get all records and find matching phone
        records = sheet.get_all_records()
        for idx, record in enumerate(records):
            if record.get('phone') == phone:
                return idx + 2  # +2 because records start at row 2 (row 1 is header)
        return None
    except Exception as e:
        print(f"ERROR finding user row for {phone}: {e}")
        return None

def update_sheet(phone, col, val, trip_type=None):
    if not sheet or not phone:
        return
    try:
        row = find_user_row(phone)
        if row:
            headers = sheet.row_values(1)
            if col in headers:
                col_idx = headers.index(col) + 1
                sheet.update_cell(row, col_idx, val)
            if trip_type and 'trip_type' in headers:
                trip_col_idx = headers.index('trip_type') + 1
                sheet.update_cell(row, trip_col_idx, trip_type)
        else:
            print(f"WARNING: User {phone} not found in sheet, creating new entry")
            # Create new entry if user doesn't exist
            sheet.append_row([datetime.now().isoformat(), phone, '', '', ''])
    except Exception as e:
        print(f"ERROR updating sheet for {phone}: {e}")

def get_user_state(phone):
    if not sheet or not phone:
        return None
    try:
        row = find_user_row(phone)
        if row:
            headers = sheet.row_values(1)
            if 'state' in headers:
                state_col = headers.index('state') + 1
                state_value = sheet.cell(row, state_col).value
                return state_value if state_value else None
        return None
    except Exception as e:
        print(f"ERROR getting user state for {phone}: {e}")
        return None

def set_user_state(phone, state):
    if not sheet or not phone:
        return
    try:
        row = find_user_row(phone)
        if row:
            headers = sheet.row_values(1)
            if 'state' in headers:
                state_col = headers.index('state') + 1
                sheet.update_cell(row, state_col, state)
        else:
            # Create new row if user doesn't exist
            sheet.append_row([datetime.now().isoformat(), phone, '', state])
    except Exception as e:
        print(f"ERROR setting user state for {phone}: {e}")

# FIX 8: Use PORT environment variable for Railway deployment
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
