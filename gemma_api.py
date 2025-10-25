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

GEMINI_API_KEY = "AIzaSyBqWOT3n3LA8hJBriMGFFrmanLfkIEjhr0"  # Geçerli API key ile değiştir
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

# 429 ve diğer hatalara karşı güvenli request
def safe_request(payload, headers, retries=5, delay=2):
    for attempt in range(retries):
        try:
            resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30)
            if resp.status_code == 429:
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise e
            time.sleep(delay)
            delay *= 2
    raise Exception("Too many requests veya bağlantı hatası, lütfen daha sonra tekrar deneyin.")

# Kullanıcı mesajını işleyip cache ve memory ile birlikte Gemini API’ye gönder
def get_gemma_response(prompt_text):
    if prompt_text in gemma_cache:
        return gemma_cache[prompt_text]

    payload = {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "Sen Nova, kişisel asistansın ve Türkçe konuşuyorsun."}]},
            {"role": "user", "content": [{"type": "text", "text": prompt_text}]}
        ],
        "temperature": 0.7
    }
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {GEMINI_API_KEY}"}
    data = safe_request(payload, headers)
    # API’den gelen yanıtı çıkar
    candidates = data.get("candidates", [])
    text = candidates[0].get("content", [{}])[0].get("text", "")
    text = text or "⚠️ Yanıt boş."
    gemma_cache[prompt_text] = text
    return text

# AFK warmup, rate limit dostu
def afk_warmup():
    warmup_interval = 120  # 2 dakika
    warmup_messages = ["Merhaba!", "Nasılsın?"]
    while True:
        time.sleep(warmup_interval)
        idle_time = time.time() - AFK_MODE["last_active"]
        if idle_time > 60:
            AFK_MODE["active"] = True
            for msg in warmup_messages:
                executor.submit(get_gemma_response, msg)
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

    # Kullanıcı hafızasını yükle
    if user_id not in user_memory:
        load_user_memory(user_id)

    # Konuşmayı hafızaya ekle
    user_memory[user_id]["conversation"].append({"role": "user", "text": user_mesaj})
    user_memory[user_id]["info"].update(user_info)

    # Prompt oluştur
    memory_context = json.dumps(user_memory[user_id], ensure_ascii=False)
    prompt = (
        f"Kullanıcıyla geçmiş konuşmalar: {memory_context}\n"
        f"Kullanıcı yeni mesajı: {user_mesaj}\n"
        "Bu bilgilere dayanarak kişisel ve ilgili bir yanıt üret ve cevabı Türkçe ver."
    )

    try:
        text = get_gemma_response(prompt)
        # Hafızaya ekle
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
