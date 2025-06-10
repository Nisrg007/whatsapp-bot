from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import firebase_admin
from firebase_admin import credentials, firestore
import re
from datetime import datetime
import json
import os

app = Flask(__name__)

# Firebase
firebase_config = json.loads(os.environ["FIREBASE_CREDENTIALS"])
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)

# Sessions
sessions = {}

languages = {"1": "hindi", "2": "gujarati"}
language_texts = {
    "hindi": {
        "welcome": "🙏 स्वागत है!\nकृपया भाषा चुनें:\n1. हिन्दी\n2. ગુજરાતી",
        "products_intro": "📦 उपलब्ध उत्पाद:\n\n",
        "enter_products": "कृपया उत्पाद और मात्रा भेजें (जैसे: प्लेट 100, कप 50)",
        "ask_days": "कितने दिनों में डिलीवरी चाहिए? (जैसे: 2)",
        "order_summary": "🧾 ऑर्डर सारांश:\n",
        "thanks": "धन्यवाद! आपका ऑर्डर रिकॉर्ड कर लिया गया है।",
        "invalid_lang": "❗कृपया 1 या 2 में से चुनें।"
    },
    "gujarati": {
        "welcome": "🙏 સ્વાગત છે!\nકૃપા કરીને ભાષા પસંદ કરો:\n1. हिन्दी\n2. ગુજરાતી",
        "products_intro": "📦 ઉપલબ્ધ ઉત્પાદનો:\n\n",
        "enter_products": "કૃપા કરીને ઉત્પાદન અને માત્રા લખો (જેમ કે: પ્લેટ 100, કપ 50)",
        "ask_days": "કેટલા દિવસમાં ડિલિવરી જોઈતી છે? (જેમ કે: 2)",
        "order_summary": "🧾 ઓર્ડર સરાંશ:\n",
        "thanks": "આભાર! તમારું ઓર્ડર નોંધાઈ ગયું છે.",
        "invalid_lang": "❗મેહરબાની કરીને 1 અથવા 2 પસંદ કરો."
    }
}

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "").strip()
    resp = MessagingResponse()
    msg = resp.message()

    if sender not in sessions:
        sessions[sender] = {"stage": "language"}
        msg.body(language_texts["hindi"]["welcome"])
        return str(resp)

    session = sessions[sender]
    lang = session.get("language", "hindi")
    texts = language_texts[lang]

    if session["stage"] == "language":
        if incoming_msg in languages:
            lang = languages[incoming_msg]
            session["language"] = lang
            session["stage"] = "show_products"
            return show_products(msg, sender, lang)
        else:
            msg.body(texts["invalid_lang"])
            return str(resp)

    elif session["stage"] == "show_products":
        return ask_for_products(msg, sender, lang)

    elif session["stage"] == "order_input":
        session["order"] = parse_products(incoming_msg)
        session["stage"] = "delivery_time"
        msg.body(texts["ask_days"])
        return str(resp)

    elif session["stage"] == "delivery_time":
        session["delivery_days"] = incoming_msg
        return summarize_order(msg, sender, lang)

    msg.body("कृपया फिर से प्रयास करें।")
    return str(resp)

def show_products(msg, sender, lang):
    texts = language_texts[lang]
    products = db.collection("products").stream()
    response = texts["products_intro"]
    for p in products:
        data = p.to_dict()
        response += f"🧾 {data['name']}\n💰 ₹{data['price']} प्रति यूनिट\n\n"
    response += texts["enter_products"]
    sessions[sender]["stage"] = "order_input"
    msg.body(response)
    return str(msg)

def ask_for_products(msg, sender, lang):
    sessions[sender]["stage"] = "order_input"
    msg.body(language_texts[lang]["enter_products"])
    return str(msg)

def parse_products(text):
    items = {}
    matches = re.findall(r'([^\d\s,]+)\s*(\d+)', text)
    for name, qty in matches:
        items[name.strip().lower()] = int(qty)
    return items

def summarize_order(msg, sender, lang):
    order = sessions[sender]["order"]
    delivery_days = sessions[sender]["delivery_days"]
    texts = language_texts[lang]

    products_ref = db.collection("products").stream()
    product_db = {p.to_dict()["name"].strip().lower(): p.to_dict() for p in products_ref}

    summary = texts["order_summary"]
    total = 0
    for name, qty in order.items():
        if name in product_db:
            price = product_db[name]["price"]
            amount = qty * price
            summary += f"{name} - {qty} × ₹{price} = ₹{amount}\n"
            total += amount
        else:
            summary += f"{name} - ❌ उत्पाद नहीं मिला\n"

    summary += f"\n🕒 डिलीवरी: {delivery_days} दिन में\n💰 कुल: ₹{total}\n\n"
    summary += texts["thanks"]

    db.collection("orders").add({
        "sender": sender,
        "language": lang,
        "order": order,
        "delivery_days": delivery_days,
        "total": total,
        "timestamp": datetime.now()
    })

    sessions.pop(sender)
    msg.body(summary)
    return str(msg)

if __name__ == "__main__":
    app.run(debug=True)
