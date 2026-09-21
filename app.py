from flask import Flask, request, jsonify, render_template_string
import base64
import hashlib
import hmac
import os
import requests
from datetime import datetime, timedelta

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from langdetect import detect, LangDetectException
from openai import OpenAI

app = Flask(__name__)

# ========== CONFIG ==========
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "safari_ug_2026")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials.json")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

PAYSTACK_LINKS = {
    "gorilla": "https://paystack.com/pay/safari-gorilla-183k",
    "murchison": "https://paystack.com/pay/safari-murchison-110k",
    "queen": "https://paystack.com/pay/safari-queen-146k",
    "custom": "https://paystack.com/pay/safari-custom-365k",
}

BUSINESSES = {
    "SAFARI_UG_001": {
        "name": "Elite Safari Bot by Snag.Ai",
        "admin_phone": ADMIN_PHONE or "+256XXXXXXXXX",
        "packages": {
            "gorilla trekking 3d2n": {"price": 4380000, "usd": 1200, "deposit": 183000},
            "murchison falls 2d1n": {"price": 1642500, "usd": 450, "deposit": 110000},
            "queen elizabeth 3d2n": {"price": 2372500, "usd": 650, "deposit": 146000},
            "custom 7 day": {"price": 10220000, "usd": 2800, "deposit": 365000},
        },
    }
}

# OpenAI client initialization
client_ai = None
if OPENAI_API_KEY:
    try:
        client_ai = OpenAI(api_key=OPENAI_API_KEY)
        print("✅ OpenAI client initialized successfully")
    except Exception as exc:  # pragma: no cover - runtime health logging
        print(f"❌ ERROR: Failed to initialize OpenAI client: {exc}")
        client_ai = None
else:
    print("⚠️  WARNING: OPENAI_API_KEY not set. Image generation will be disabled.")

# Google Sheets
sheet = None


def write_google_credentials_if_needed():
    if not GOOGLE_CREDENTIALS_JSON:
        return os.path.exists(GOOGLE_CREDENTIALS_PATH)

    try:
        os.makedirs(os.path.dirname(GOOGLE_CREDENTIALS_PATH) or ".", exist_ok=True)
        with open(GOOGLE_CREDENTIALS_PATH, "wb") as fh:
            fh.write(base64.b64decode(GOOGLE_CREDENTIALS_JSON))
        return True
    except Exception as exc:
        print(f"❌ ERROR: Failed to write Google credentials: {exc}")
        return False


def ensure_sheet_schema():
    global sheet
    if not sheet:
        return False

    try:
        headers = sheet.row_values(1)
        if not headers:
            required = [
                "created_at",
                "phone",
                "trip_type",
                "dates",
                "pax",
                "trip_status",
                "payment_status",
                "state",
                "notes",
            ]
            sheet.append_row(required)
            headers = required

        required = [
            "created_at",
            "phone",
            "trip_type",
            "dates",
            "pax",
            "trip_status",
            "payment_status",
            "state",
            "notes",
        ]
        missing = [header for header in required if header not in headers]
        if missing:
            headers = headers + missing
            sheet.update("A1", [headers])
        return True
    except Exception as exc:
        print(f"❌ ERROR: Failed to ensure sheet schema: {exc}")
        return False


def init_google_sheet():
    global sheet
    if sheet is not None:
        return sheet

    if not write_google_credentials_if_needed():
        print("⚠️  WARNING: Google credentials unavailable. Google Sheets integration disabled.")
        return None

    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
        client = gspread.authorize(creds)

        try:
            workbook = client.open("Elite_Safari_DB")
        except gspread.exceptions.SpreadsheetNotFound:
            workbook = client.create("Elite_Safari_DB")

        if workbook.worksheets():
            sheet = workbook.get_worksheet(0)
        else:
            sheet = workbook.add_worksheet(title="Sheet1", rows=1000, cols=30)

        ensure_sheet_schema()
        print("✅ Google Sheets connected successfully")
        return sheet
    except FileNotFoundError:
        print("⚠️  WARNING: Google credentials file not found. Google Sheets integration disabled.")
    except Exception as exc:
        print(f"❌ ERROR: Failed to connect to Google Sheets: {exc}")
    return None


sheet = init_google_sheet()

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
            n=1,
        )

        image_url = None
        if hasattr(response, "data") and response.data:
            image_obj = response.data[0]
            if hasattr(image_obj, "url"):
                image_url = image_obj.url
            elif isinstance(image_obj, dict):
                image_url = image_obj.get("url")

        if not image_url:
            raise ValueError("No image URL returned from AI")

        print(f"✅ Image generated successfully: {image_url}")
        send_image(phone, image_url, "Sample photo. Actual lodge may vary.")
        if sheet:
            sheet.append_row([datetime.now().isoformat(), phone, "ai_image_request", "", "", "", "", "", prompt])
    except Exception as exc:
        print(f"❌ ERROR generating image: {exc}")
        send_message(phone, "Sorry, couldn't generate image. Please try again later.")


# ========== ADMIN DASHBOARD ==========
def admin_authorized():
    if not ADMIN_TOKEN:
        return False
    provided = request.args.get("token") or request.headers.get("X-Admin-Token")
    return provided == ADMIN_TOKEN


@app.route("/admin", methods=["GET"])
def admin_dashboard():
    if not admin_authorized():
        return "Forbidden", 403

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
        paid = len([r for r in records if str(r.get("payment_status", "")).upper() == "PAID"])
        trips = len([r for r in records if str(r.get("trip_status", "")).upper() == "CONFIRMED"])
        return render_template_string(html, records=records, total=len(records), paid=paid, trips=trips)
    except Exception as exc:
        print(f"ERROR in admin_dashboard: {exc}")
        return "Error loading dashboard", 500


# ========== HEALTH CHECK ==========
@app.route("/health", methods=["GET"])
def health_check():
    status = {
        "status": "healthy",
        "whatsapp_configured": bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID),
        "openai_configured": bool(client_ai is not None),
        "google_sheets_configured": bool(sheet is not None),
        "admin_configured": bool(ADMIN_TOKEN),
        "timestamp": datetime.now().isoformat(),
    }
    return jsonify(status), 200


# ========== WEBHOOK ==========
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        challenge = request.args.get("hub.challenge")
        return challenge or "", 200
    return "Invalid token", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True)
        if data and "entry" in data and len(data["entry"]) > 0:
            if "changes" in data["entry"][0] and len(data["entry"][0]["changes"]) > 0:
                if "value" in data["entry"][0]["changes"][0]:
                    value = data["entry"][0]["changes"][0]["value"]
                    if "messages" in value and len(value["messages"]) > 0:
                        msg = value["messages"][0]
                        phone = msg.get("from")

                        if not phone:
                            print("ERROR: No phone number in webhook")
                            return "OK", 200

                        text = msg.get("text", {}).get("body", "").lower().strip() if isinstance(msg.get("text"), dict) else ""

                        lang = "en"
                        if len(text) > 3:
                            try:
                                lang = detect(text)
                            except LangDetectException:
                                lang = "en"

                        if text and phone:
                            handle_message(phone, text, lang)
                        if msg.get("type") == "image" and "image" in msg:
                            save_document(phone, msg["image"].get("id"), "passport")
    except Exception as exc:
        print(f"ERROR in webhook: {exc}")
    return "OK", 200


# ========== SAFARI FLOWS ==========
def handle_message(phone, text, lang):
    if not phone or not isinstance(phone, str):
        print(f"ERROR: Invalid phone number: {phone}")
        return

    user_state = get_user_state(phone)

    if text in ["hi", "hello", "start", "safari"]:
        send_message(
            phone,
            """Elite Safari Bot: Karibu Uganda! 🦁

I plan gorilla trekking, Murchison Falls, Queen Elizabeth safaris.

Choose your trip:
1. Gorilla trekking Bwindi/Mgahinga - $1,200/pax
2. Murchison Falls 2D/1N - $450/pax
3. Queen Elizabeth 3D/2N - $650/pax
4. Custom 7 Day Safari - $2,800/pax

Reply 1, 2, 3, or 4""",
        )
        set_user_state(phone, "awaiting_trip")

    elif user_state == "awaiting_trip" and text == "1":
        set_user_state(phone, "gorilla_dates")
        send_message(
            phone,
            """Gorilla trekking 🦍 - Best experience in Africa!

Send me:
1. Travel dates
2. Number of people
3. Passport photos for permit booking

Permits sell out 3 months early. Reply DONE when sent.""",
        )

    elif user_state == "awaiting_trip" and text == "2":
        set_user_state(phone, "murchison_dates")
        send_message(
            phone,
            """Murchison Falls Safari 2D/1N 🦒

Send dates and number of people.
Includes: Game drive, boat cruise, accommodation, guide.
Reply DONE when sent.""",
        )

    elif user_state == "awaiting_trip" and text == "3":
        set_user_state(phone, "queen_dates")
        send_message(
            phone,
            """Queen Elizabeth 3D/2N 🦓

Send dates and number of people.
Includes: Game drive, boat cruise, accommodation, guide.
Reply DONE when sent.""",
        )

    elif user_state == "awaiting_trip" and text == "4":
        set_user_state(phone, "custom_dates")
        send_message(
            phone,
            """Custom 7 Day Safari 🦁

Send me:
1. Travel dates
2. Number of people
3. Your interests (wildlife, hiking, culture, etc)

We'll customize your perfect safari! Reply DONE when sent.""",
        )

    elif "show me" in text and ("gorilla" in text or "bwindi" in text or "lodge" in text or "lion" in text):
        if "gorilla" in text or "bwindi" in text:
            generate_safari_image("Bwindi Impenetrable Forest gorilla trekking Uganda", phone)
        elif "lodge" in text:
            generate_safari_image("Luxury safari lodge Uganda savannah", phone)
        elif "lion" in text:
            generate_safari_image("Lion in Queen Elizabeth National Park Uganda", phone)

    elif text == "done":
        if user_state == "gorilla_dates":
            send_message(
                phone,
                f"""Gorilla trip details saved ✅

Package: $1,200 per person
Deposit: $50 USD / 183,000 UGX holds permits today
Balance: Due 30 days before trip

Pay deposit: {PAYSTACK_LINKS['gorilla']}
Reply PAID after payment.""",
            )
            set_user_state(phone, "awaiting_payment_gorilla")

        elif user_state == "murchison_dates":
            send_message(
                phone,
                f"""Murchison trip saved ✅

Package: $450 per person
Deposit: $30 USD / 110,000 UGX confirms booking

Pay deposit: {PAYSTACK_LINKS['murchison']}
Reply PAID after payment.""",
            )
            set_user_state(phone, "awaiting_payment_murchison")

        elif user_state == "queen_dates":
            send_message(
                phone,
                f"""Queen Elizabeth trip saved ✅

Package: $650 per person
Deposit: $40 USD / 146,000 UGX confirms booking

Pay deposit: {PAYSTACK_LINKS['queen']}
Reply PAID after payment.""",
            )
            set_user_state(phone, "awaiting_payment_queen")

        elif user_state == "custom_dates":
            send_message(
                phone,
                f"""Custom safari details saved ✅

Package: $2,800 per person (7 days)
Deposit: $100 USD / 365,000 UGX confirms booking

Pay deposit: {PAYSTACK_LINKS['custom']}
Reply PAID after payment.""",
            )
            set_user_state(phone, "awaiting_payment_custom")

    elif text == "paid":
        if user_state and "gorilla" in user_state:
            update_sheet(phone, "payment_status", "PAID", "gorilla trekking 3d2n")
            update_sheet(phone, "trip_status", "Confirmed")
            send_message(
                phone,
                """Payment confirmed ✅ 183,000 UGX

Permits booked! PDF confirmation in 24hrs.
WhatsApp group created with your guide.
He contacts you 3 days before trip.

Reply CONFIRM when packed. Karibu Uganda!""",
            )
            notify_admin(f"GORILLA BOOKING PAID: {phone}")

        elif user_state and "murchison" in user_state:
            update_sheet(phone, "payment_status", "PAID", "murchison falls 2d1n")
            update_sheet(phone, "trip_status", "Confirmed")
            send_message(
                phone,
                """Payment confirmed ✅ 110,000 UGX

Safari confirmed! Guide contacts you 2 days before.
Pickup: Entebbe/Kampala 6:00 AM""",
            )

        elif user_state and "queen" in user_state:
            update_sheet(phone, "payment_status", "PAID", "queen elizabeth 3d2n")
            update_sheet(phone, "trip_status", "Confirmed")
            send_message(
                phone,
                """Payment confirmed ✅ 146,000 UGX

Safari confirmed! Guide contacts you 2 days before.
Pickup: Entebbe/Kampala 6:00 AM""",
            )

        elif user_state and "custom" in user_state:
            update_sheet(phone, "payment_status", "PAID", "custom 7 day")
            update_sheet(phone, "trip_status", "Confirmed")
            send_message(
                phone,
                """Payment confirmed ✅ 365,000 UGX

Custom safari confirmed! Our team will contact you within 24hrs to finalize details.
Guide contacts you 5 days before trip.

Karibu Uganda!""",
            )

    elif text == "confirm":
        update_sheet(phone, "trip_status", "Confirmed")
        send_message(phone, "Confirmed ✅ Guide will meet you at pickup point. Safe travels!")


# ========== TRIP REMINDER CRON ==========
@app.route("/cron/reminders", methods=["GET"])
def send_reminders():
    if not sheet:
        return "Google Sheets not configured", 503

    today = datetime.now().date()
    try:
        for row in sheet.get_all_records():
            if row.get("dates"):
                try:
                    dates_str = row.get("dates", "")
                    if not dates_str:
                        continue
                    date_parts = dates_str.split(",")
                    if len(date_parts) == 0:
                        continue
                    trip_date = datetime.strptime(date_parts[0].strip(), "%Y-%m-%d").date()
                    days_left = (trip_date - today).days
                    if days_left in [7, 3, 1]:
                        msg = f"Reminder: {row['trip_type']} in {days_left} day(s) on {trip_date}. Pickup: Entebbe 6:00 AM. Bring passport."
                        send_message(row["phone"], msg)
                except (ValueError, IndexError, KeyError) as exc:
                    print(f"Could not parse date: {row.get('dates', 'N/A')} - {exc}")
    except Exception as exc:
        print(f"ERROR in send_reminders: {exc}")
    return "Reminders sent", 200


# ========== PAYSTACK WEBHOOK ==========
@app.route("/paystack/webhook", methods=["POST"])
def paystack_webhook():
    if not PAYSTACK_SECRET:
        return jsonify({"status": "rejected", "message": "Paystack secret not configured"}), 401

    payload = request.get_data()
    signature = request.headers.get("X-Paystack-Signature", "")
    expected = hmac.new(PAYSTACK_SECRET.encode("utf-8"), payload, hashlib.sha512).hexdigest()

    if not signature or not hmac.compare_digest(expected, signature):
        print("ERROR: Invalid Paystack signature")
        return jsonify({"status": "rejected", "message": "Invalid signature"}), 401

    try:
        data = request.get_json(silent=True) or {}
        if data and data.get("event") == "charge.success":
            phone = data.get("data", {}).get("metadata", {}).get("phone")
            if phone:
                update_sheet(phone, "payment_status", "PAID")
                send_message(phone, "Payment confirmed ✅ Trip confirmed. Check WhatsApp for guide contact.")
            else:
                print("ERROR: Missing phone in paystack webhook")
    except Exception as exc:
        print(f"ERROR in paystack_webhook: {exc}")
    return jsonify({"status": "success"})


# ========== HELPERS ==========
def send_message(phone, message):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERROR: WhatsApp credentials not configured")
        return

    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": phone, "text": {"body": message}}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code not in (200, 201):
            print(f"ERROR: WhatsApp API returned {response.status_code}: {response.text}")
    except Exception as exc:
        print(f"ERROR sending message to {phone}: {exc}")


def send_image(phone, image_url, caption):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERROR: WhatsApp credentials not configured")
        return

    try:
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        data = {"messaging_product": "whatsapp", "to": phone, "type": "image", "image": {"link": image_url, "caption": caption}}
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code not in (200, 201):
            print(f"ERROR: WhatsApp image API returned {response.status_code}: {response.text}")
    except Exception as exc:
        print(f"ERROR sending image to {phone}: {exc}")


def notify_admin(message):
    if not ADMIN_PHONE:
        print("INFO: ADMIN_PHONE not configured; notification skipped.")
        return

    try:
        send_message(ADMIN_PHONE, f"🚨 SAFARI ALERT: {message}")
    except Exception as exc:
        print(f"ERROR notifying admin: {exc}")


def save_document(phone, media_id, doc_type):
    try:
        if sheet and phone and media_id:
            sheet.append_row([datetime.now().isoformat(), phone, doc_type, media_id, get_user_state(phone)])
    except Exception as exc:
        print(f"ERROR saving document: {exc}")


def find_user_row(phone):
    if not sheet or not phone:
        return None

    try:
        records = sheet.get_all_records()
        normalized = str(phone).strip()
        for idx, record in enumerate(records):
            if str(record.get("phone", "")).strip() == normalized:
                return idx + 2
        return None
    except Exception as exc:
        print(f"ERROR finding user row for {phone}: {exc}")
        return None


def update_sheet(phone, col, val, trip_type=None):
    if not sheet or not phone:
        return

    try:
        ensure_sheet_schema()
        row = find_user_row(phone)
        headers = sheet.row_values(1)

        if row:
            if col in headers:
                col_idx = headers.index(col) + 1
                sheet.update_cell(row, col_idx, val)
            if trip_type and "trip_type" in headers:
                trip_col_idx = headers.index("trip_type") + 1
                sheet.update_cell(row, trip_col_idx, trip_type)
            return

        print(f"WARNING: User {phone} not found in sheet, creating new entry")
        empty_row = [""] * len(headers)
        if "phone" in headers:
            empty_row[headers.index("phone")] = phone
        if "created_at" in headers:
            empty_row[headers.index("created_at")] = datetime.now().isoformat()
        if "state" in headers and col == "state":
            empty_row[headers.index("state")] = val
        if trip_type and "trip_type" in headers:
            empty_row[headers.index("trip_type")] = trip_type
        if col in headers and col != "state":
            empty_row[headers.index(col)] = val
        sheet.append_row(empty_row)
    except Exception as exc:
        print(f"ERROR updating sheet for {phone}: {exc}")


def get_user_state(phone):
    if not sheet or not phone:
        return None

    try:
        row = find_user_row(phone)
        if row:
            headers = sheet.row_values(1)
            if "state" in headers:
                state_col = headers.index("state") + 1
                state_value = sheet.cell(row, state_col).value
                return state_value if state_value else None
        return None
    except Exception as exc:
        print(f"ERROR getting user state for {phone}: {exc}")
        return None


def set_user_state(phone, state):
    if not sheet or not phone:
        return

    try:
        ensure_sheet_schema()
        row = find_user_row(phone)
        headers = sheet.row_values(1)

        if row:
            if "state" in headers:
                state_col = headers.index("state") + 1
                sheet.update_cell(row, state_col, state)
            return

        empty_row = [""] * len(headers)
        if "phone" in headers:
            empty_row[headers.index("phone")] = phone
        if "state" in headers:
            empty_row[headers.index("state")] = state
        if "created_at" in headers:
            empty_row[headers.index("created_at")] = datetime.now().isoformat()
        sheet.append_row(empty_row)
    except Exception as exc:
        print(f"ERROR setting user state for {phone}: {exc}")


# ========== APP START ==========
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
