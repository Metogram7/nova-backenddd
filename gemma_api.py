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

gemma_cache = {}
user_memory = {}
AFK_MODE = {"active": False, "last_active": time.time(), "speed_multiplier": 1.0}
executor = ThreadPoolExecutor(max_workers=5)

GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"  # Google Gemini API Key
MODEL_NAME = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

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

def warmup_message(msg):
    if msg in gemma_cache:
        return
    try:
        payload = {"contents":[{"parts":[{"text":msg}]}]}
        headers = {"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}
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
        if idle_time > 60:  # 1 dk AFK
            AFK_MODE["active"] = True
            for msg in ["Merhaba!", "Nasılsın?", "Hava bugün nasıl?", "Selam!"]:
                executor.submit(warmup_message, msg)
            AFK_MODE["speed_multiplier"] = 0.5
        else:
            AFK_MODE["active"] = False
            AFK_MODE["speed_multiplier"] = 1.0

threading.Thread(target=afk_warmup, daemon=True).start()

# --- API Route ---
@app.route("/gemma", methods=["POST"])
def gemma():
    req_json = request.json
    user_id = req_json.get("userId", "default")
    user_mesaj = req_json.get("message", "")
    user_info = req_json.get("userInfo", {})

    if not user_mesaj:
        return jsonify({"response": "Mesaj boş"}), 400

    AFK_MODE["last_active"] = time.time()
    speed = AFK_MODE["speed_multiplier"]

    # Kullanıcı hafızasını yükle
    if user_id not in user_memory:
        load_user_memory(user_id)

    # Konuşmayı hafızaya ekle
    user_memory[user_id]["conversation"].append({"role": "user", "text": user_mesaj})

    # Kullanıcı bilgilerini güncelle
    user_memory[user_id]["info"].update(user_info)

    # Prompt oluştur
    memory_context = json.dumps(user_memory[user_id], ensure_ascii=False)
    prompt = (
        f"Kullanıcıyla geçmiş konuşmalar: {memory_context}\n"
        f"Kullanıcı yeni mesajı: {user_mesaj}\n"
        "Bu bilgilere dayanarak kişisel ve ilgili bir yanıt üret ve cevabı Türkçe ver."
    )

    payload = {"contents":[{"parts":[{"text":prompt}]}]}
    headers = {"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}

    try:
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30*speed)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        text = text or "⚠️ Yanıt boş."

        # Cache ve hafıza güncelle
        gemma_cache[user_mesaj] = text
        user_memory[user_id]["conversation"].append({"role": "nova", "text": text})
        save_user_memory(user_id)

        return jsonify({"response": text})
    except Exception as e:
        return jsonify({"response": f"⚠️ Hata: {e}"}), 500

# --- Sunucu Başlat ---
if __name__ == "__main__":
    from gevent.pywsgi import WSGIServer
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Nova backend {port} portunda çalışıyor... (Hafıza: {DATA_DIR})")
    http_server = WSGIServer(('0.0.0.0', port), app)
    http_server.serve_forever()
