from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)

# --- Cache ve AFK yönetimi ---
gemma_cache = {}
AFK_MODE = {"active": False, "last_active": time.time(), "speed_multiplier": 1.0}
executor = ThreadPoolExecutor(max_workers=5)

GEMINI_API_KEY = "AIzaSyBqWOT3n3LA8hJBriMGFFrmanLfkIEjhr0"
MODEL_NAME = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# --- Paralel mesaj ısınma ---
def warmup_message(msg):
    if msg in gemma_cache:
        return
    try:
        payload = {"contents":[{"parts":[{"text":msg}]}]}
        headers = {"Content-Type":"application/json", "x-goog-api-key": GEMINI_API_KEY}
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        gemma_cache[msg] = text
    except:
        gemma_cache[msg] = "⚠️ Hazırlık hatası"

def afk_warmup():
    while True:
        time.sleep(10)
        idle_time = time.time() - AFK_MODE["last_active"]
        if idle_time > 60:  # 1 dakika AFK
            AFK_MODE["active"] = True
            test_messages = ["Merhaba!", "Nasılsın?", "Hava bugün nasıl?", "Bugün hava güzel mi?", "Selam!"]
            for msg in test_messages:
                executor.submit(warmup_message, msg)
            AFK_MODE["speed_multiplier"] = 0.5  # yarı sürede yanıt
        else:
            AFK_MODE["active"] = False
            AFK_MODE["speed_multiplier"] = 1.0

threading.Thread(target=afk_warmup, daemon=True).start()

# --- API Route ---
@app.route("/gemma", methods=["POST"])
def gemma():
    user_mesaj = request.json.get("message", "")
    if not user_mesaj:
        return jsonify({"response": "Mesaj boş"}), 400

    # Kullanıcı aktifliği
    AFK_MODE["last_active"] = time.time()
    speed = AFK_MODE["speed_multiplier"]

    # Cache kontrol
    if user_mesaj in gemma_cache:
        return jsonify({"response": gemma_cache[user_mesaj]})

    # API çağrısı
    payload = {"contents":[{"parts":[{"text":user_mesaj}]}]}
    headers = {"Content-Type":"application/json", "x-goog-api-key": GEMINI_API_KEY}

    try:
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30*speed)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        gemma_cache[user_mesaj] = text or "⚠️ Yanıt boş."
        return jsonify({"response": gemma_cache[user_mesaj]})
    except Exception as e:
        return jsonify({"response": f"⚠️ Hata: {e}"}), 500

# --- Sunucu başlatma (Gevent) ---
if __name__ == "__main__":
    from gevent.pywsgi import WSGIServer
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Nova backend {port} portunda çalışıyor...")
    http_server = WSGIServer(('0.0.0.0', port), app)
    http_server.serve_forever()
