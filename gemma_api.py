from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import threading
import time

app = Flask(__name__)
CORS(app)
gemma_cache = {}
AFK_MODE = {"active": False, "last_active": time.time(), "speed_multiplier": 1.0}

GEMINI_API_KEY = "AIzaSyBqWOT3n3LA8hJBriMGFFrmanLfkIEjhr0"
MODEL_NAME = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# AFK ısınma fonksiyonu
def afk_warmup():
    while True:
        time.sleep(10)
        if time.time() - AFK_MODE["last_active"] > 60:  # 1 dakika AFK
            AFK_MODE["active"] = True
            # Örnek: cache ısınması
            test_messages = ["Merhaba!", "Nasılsın?", "Hava bugün nasıl?"]
            for msg in test_messages:
                if msg not in gemma_cache:
                    try:
                        payload = {"contents":[{"parts":[{"text":msg}]}]}
                        headers = {"Content-Type":"application/json", "x-goog-api-key": GEMINI_API_KEY}
                        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=10)
                        resp.raise_for_status()
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        gemma_cache[msg] = text
                    except:
                        continue
            # Hız çarpanı
            AFK_MODE["speed_multiplier"] = 0.5  # yarı sürede yanıt
        else:
            AFK_MODE["active"] = False
            AFK_MODE["speed_multiplier"] = 1.0

threading.Thread(target=afk_warmup, daemon=True).start()

@app.route("/gemma", methods=["POST"])
def gemma():
    user_mesaj = request.json.get("message", "")
    if not user_mesaj:
        return jsonify({"response": "Mesaj boş"}), 400

    AFK_MODE["last_active"] = time.time()  # kullanıcı aktif
    speed = AFK_MODE["speed_multiplier"]

    if user_mesaj in gemma_cache:
        return jsonify({"response": gemma_cache[user_mesaj]})

    payload = {"contents":[{"parts":[{"text":user_mesaj}]}]}
    headers = {"Content-Type":"application/json", "x-goog-api-key": GEMINI_API_KEY}

    try:
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=60*speed)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        gemma_cache[user_mesaj] = text or "⚠️ Yanıt boş."
        return jsonify({"response": gemma_cache[user_mesaj]})
    except Exception as e:
        return jsonify({"response": f"⚠️ Hata: {e}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
