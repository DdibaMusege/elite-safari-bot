from flask import Flask, request, jsonify, render_template_string
import requests, os, datetime
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from langdetect import detect
from openai import OpenAI

app = Flask(__name__)

# ========== CONFIG ==========
VERIFY_TOKEN = "safari_ug_2026"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
OPENAI_KEY = os.getenv("OPENAI_KEY")
client_ai = OpenAI(api_key=OPENAI_KEY)

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
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Elite_Safari_DB").sheet1

# ========== AI IMAGE GENERATOR ==========
def generate_safari_image(prompt, phone):
    response = client_ai.images.generate(
        model="dall-e-3",
        prompt=f"{prompt}, Uganda safari, professional tourism photo, watermark 'SAMPLE ONLY'",
        size="1024x1024",
        quality="standard",
        n=1
    )
    image_url = response.data[0].url
    send_image(phone, image_url, "Sample photo. Actual lodge may vary.")
    sheet.append_row([datetime.now().isoformat(), phone, 'ai_image_request', prompt])

# ========== ADMIN DASHBOARD ==========
@app.route('/admin', methods=['GET'])
def admin_dashboard():
    records = sheet.get_all_records()
    html = """
    <html><head><title>Elite Safari Bot Admin</title>
    <style>body{font-family:Arial;padding:20px} table{border-collapse:collapse;width:100%}
    th,td{border:1px solid #ddd;padding:8px;text-align:left} th{background:#FF6B35;color:white}</style>
    </head><body>
    <h2>Elite Safari Bot - Live Dashboard</h2>
    <p>Total Leads: {{total}} | Paid: {{paid}} | Trips This Week: {{trips}}</p>
    <table><tr><th>Phone</th><th>Trip</th><th>Dates</th><th>Pax</th><th>Status</th><th>Payment</th></tr>
    {% for r in records %}
    <tr><td>{{r.phone}}</td><td>{{r.trip_type}}</td><td>{{r.dates}}</td><td>{{r.pax}}</td><td>{{r.trip_status}}</td><td>{{r.payment_status}}</td></tr>
    {% endfor %}</table></body></html>
    """
    paid = len([r for r in records if r.get('payment_status') == 'PAID'])
    trips = len([r for r in records if r.get('trip_status') == 'Confirmed'])
    return render_template_string(html, records=records, total=len(records), paid=paid, trips=trips)

# ========== WEBHOOK ==========
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return 'Invalid token', 403

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'messages' in data['entry'][0]['changes'][0]['value']:
        msg = data['entry'][0]['changes'][0]['value']['messages'][0]
        phone = msg['from']
        text = msg.get('text', {}).get('body', '').lower()
        lang = detect(text) if len(text) > 3 else 'en'

        if text: handle_message(phone, text, lang)
        if msg.get('type') == 'image': save_document(phone, msg['image']['id'], 'passport')
    return 'OK', 200

# ========== SAFARI FLOWS ==========
def handle_message(phone, text, lang):
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

    elif 'show me' in text:
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
Deposit: $50 / 183,000 UGX holds permits today
Balance: Due 30 days before trip

Pay deposit: {PAYSTACK_LINKS['gorilla']}
Reply PAID after payment.""")
            set_user_state(phone, 'awaiting_payment_gorilla')

        elif user_state == 'murchison_dates':
            send_message(phone, f"""Murchison trip saved ✅

Package: $450 per person
Deposit: $30 / 110,000 UGX confirms booking

Pay deposit: {PAYSTACK_LINKS['murchison']}
Reply PAID after payment.""")
            set_user_state(phone, 'awaiting_payment_murchison')

    elif text == 'paid':
        if 'gorilla' in user_state:
            update_sheet(phone, 'payment_status', 'PAID', 'gorilla trekking 3d2n')
            update_sheet(phone, 'trip_status', 'Confirmed')
            send_message(phone, """Payment confirmed ✅ 183,000 UGX

Permits booked! PDF confirmation in 24hrs.
WhatsApp group created with your guide.
He contacts you 3 days before trip.

Reply CONFIRM when packed. Karibu Uganda!""")
            notify_admin(f"GORILLA BOOKING PAID: {phone}")

        elif 'murchison' in user_state:
            update_sheet(phone, 'payment_status', 'PAID', 'murchison falls 2d1n')
            update_sheet(phone, 'trip_status', 'Confirmed')
            send_message(phone, """Payment confirmed ✅ 110,000 UGX

Safari confirmed! Guide contacts you 2 days before.
Pickup: Entebbe/Kampala 6:00 AM""")

    elif text == 'confirm':
        update_sheet(phone, 'trip_status', 'Confirmed')
        send_message(phone, "Confirmed ✅ Guide will meet you at pickup point. Safe travels!")

# ========== TRIP REMINDER CRON ==========
@app.route('/cron/reminders', methods=['GET'])
def send_reminders():
    today = datetime.now().date()
    for row in sheet.get_all_records():
        if row.get('dates'):
            try:
                trip_date = datetime.strptime(row['dates'].split(',')[0], '%Y-%m-%d').date()
                days_left = (trip_date - today).days
                if days_left in [7, 3, 1]:
                    msg = f"Reminder: {row['trip_type']} in {days_left} day(s) on {trip_date}. Pickup: Entebbe 6:00 AM. Bring passport."
                    send_message(row['phone'], msg)
            except: pass
    return 'Reminders sent', 200

# ========== PAYSTACK WEBHOOK ==========
@app.route('/paystack/webhook', methods=['POST'])
def paystack_webhook():
    data = request.json
    if data['event'] == 'charge.success':
        phone = data['data']['metadata']['phone']
        update_sheet(phone, 'payment_status', 'PAID')
        send_message(phone, "Payment confirmed ✅ Trip confirmed. Check WhatsApp for guide contact.")
    return jsonify({'status': 'success'})

# ========== HELPERS ==========
def send_message(phone, message):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    requests.post(url, headers=headers, json={"messaging_product": "whatsapp", "to": phone, "text": {"body": message}})

def send_image(phone, image_url, caption):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    data = {"messaging_product": "whatsapp", "to": phone, "type": "image", "image": {"link": image_url, "caption": caption}}
    requests.post(url, headers=headers, json=data)

def notify_admin(message):
    admin = BUSINESSES["SAFARI_UG_001"]["admin_phone"]
    send_message(admin, f"🚨 SAFARI ALERT: {message}")

def save_document(phone, media_id, doc_type):
    sheet.append_row([datetime.now().isoformat(), phone, doc_type, media_id, get_user_state(phone)])

def update_sheet(phone, col, val, trip_type=None):
    try:
        cell = sheet.find(phone)
        sheet.update_cell(cell.row, sheet.find(col).col, val)
        if trip_type: sheet.update_cell(cell.row, sheet.find('trip_type').col, trip_type)
    except: pass

def get_user_state(phone):
    try: return sheet.cell(sheet.find(phone).row, sheet.find('state').col).value
    except: return None

def set_user_state(phone, state):
    try:
        cell = sheet.find(phone)
        sheet.update_cell(cell.row, sheet.find('state').col, state)
    except: sheet.append_row([datetime.now().isoformat(), phone, '', state])

if __name__ == '__main__':
    app.run(port=5000)