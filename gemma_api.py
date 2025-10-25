from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)

# --- Ayarlar ---
DATA_DIR = r"D:\kullanıcılar"
os.makedirs(DATA_DIR, exist_ok=True)

nova_cache = {}
user_memory = {}
AFK_MODE = {"active": False, "last_active": time.time(), "speed_multiplier": 1.0}
executor = ThreadPoolExecutor(max_workers=5)

GEMINI_API_KEY = "AIzaSyBqWOT3n3LA8hJBriMGFFrmanLfkIEjhr0"
MODEL_NAME = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# --- Nova bilgisi ---
DEFAULT_NOVA_INFO = {
    "ad": "Nova",
    "gelistirici": "Metehan",
    "tarih": time.strftime("%Y-%m-%d")
}

# --- Yardımcı Fonksiyonlar ---
def get_user_path(user_id):
    return os.path.join(DATA_DIR, f"user_{user_id}.json")

def load_user_memory(user_id):
    path = get_user_path(user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user_memory[user_id] = json.load(f)
    else:
        user_memory[user_id] = {"info": {}, "conversation": []}

def save_user_memory(user_id):
    path = get_user_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(user_memory[user_id], f, ensure_ascii=False, indent=2)

# --- AFK ve paralel hazırlık ---
def warmup_message(msg):
    if msg in nova_cache: return
    try:
        payload = {"contents":[{"parts":[{"text":msg}]}]}
        headers = {"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        nova_cache[msg] = text
    except:
        nova_cache[msg] = "⚠️ Hazırlık hatası"

def afk_warmup():
    while True:
        time.sleep(10)
        idle_time = time.time() - AFK_MODE["last_active"]
        if idle_time > 60:
            AFK_MODE["active"] = True
            for msg in ["Merhaba!", "Nasılsın?", "Hava bugün nasıl?", "Selam!"]:
                executor.submit(warmup_message, msg)
            AFK_MODE["speed_multiplier"] = 0.5
        else:
            AFK_MODE["active"] = False
            AFK_MODE["speed_multiplier"] = 1.0

threading.Thread(target=afk_warmup, daemon=True).start()

# --- Nova API ---
@app.route("/nova", methods=["POST"])
def nova():
    try:
        req_json = request.json
        user_id = req_json.get("userId", "default")
        user_mesaj = req_json.get("message", "")
        user_info = req_json.get("userInfo", {})

        if not user_mesaj:
            return jsonify({"response": "Mesaj boş"}), 400

        AFK_MODE["last_active"] = time.time()
        speed = AFK_MODE["speed_multiplier"]

        if user_id not in user_memory:
            load_user_memory(user_id)

        # Konuşmayı ve kullanıcı bilgilerini ekle
        user_memory[user_id]["conversation"].append({"role": "user", "text": user_mesaj})
        user_memory[user_id]["info"].update(user_info)
        user_memory[user_id]["info"].update(DEFAULT_NOVA_INFO)

        # Prompt oluştur
        memory_context = json.dumps(user_memory[user_id], ensure_ascii=False)
        prompt = (
            f"Kullanıcıyla geçmiş konuşmalar: {memory_context}\n"
            f"Kullanıcı yeni mesajı: {user_mesaj}\n"
            "Bu bilgilere dayanarak kişisel ve ilgili bir yanıt üret ve cevabı Türkçe ver."
        )

        # Cache kontrolü
        if user_mesaj in nova_cache:
            text = nova_cache[user_mesaj]
        else:
            payload = {"contents":[{"parts":[{"text":prompt}]}]}
            headers = {"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}

            resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30*speed)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                text = "Merhaba! Nova seni duyuyor."
            nova_cache[user_mesaj] = text

        user_memory[user_id]["conversation"].append({"role": "nova", "text": text})
        save_user_memory(user_id)

        return jsonify({"response": text})

    except Exception as e:
        return jsonify({"response": f"Merhaba! ⚠️ API hatası: {e}"})

# --- Sunucu Başlat ---
if __name__ == "__main__":
    from gevent.pywsgi import WSGIServer
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Nova backend {port} portunda çalışıyor... (Hafıza: {DATA_DIR})")
    http_server = WSGIServer(('0.0.0.0', port), app)
    http_server.serve_forever()
