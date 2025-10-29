from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import json
import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)

# --- Ayarlar ---
DATA_DIR = os.path.join(os.getcwd(), "kullanicilar")
os.makedirs(DATA_DIR, exist_ok=True)

gemma_cache = {}
user_memory = {}
AFK_MODE = {"active": False, "last_active": time.time(), "speed_multiplier": 1.0}
executor = ThreadPoolExecutor(max_workers=5)

# ✅ Senin API key’in buraya yazıldı (sadece test için)
GEMINI_API_KEY = "AIzaSyBfzoyaMSbSN7PV1cIhhKIuZi22ZY6bhP8"
MODEL_NAME = "gemini-2.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_API_URL = f"{GEMINI_API_BASE}/{MODEL_NAME}:generateContent"


# --- Yardımcı Fonksiyonlar ---
def get_user_path(user_id):
    return os.path.join(DATA_DIR, f"user_{user_id}.json")

def load_user_memory(user_id):
    path = get_user_path(user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                user_memory[user_id] = json.load(f)
            except Exception:
                user_memory[user_id] = {"info": {}, "conversation": []}
    else:
        user_memory[user_id] = {"info": {}, "conversation": []}

def save_user_memory(user_id):
    path = get_user_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(user_memory[user_id], f, ensure_ascii=False, indent=2)


# --- Güvenli İstek ---
def safe_request(payload, retries=3, delay=3):
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY tanımlı değil.")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    last_exc = None
    for attempt in range(1, retries+1):
        try:
            resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30)
            if resp.status_code != 200:
                text = resp.text
                if resp.status_code == 429:
                    time.sleep(delay)
                    continue
                raise Exception(f"HTTP {resp.status_code} - {text}")
            return resp.json()
        except Exception as e:
            last_exc = e
            app.logger.error(f"safe_request attempt {attempt} failed: {e}\n{traceback.format_exc()}")
            if attempt < retries:
                time.sleep(delay)
    raise Exception(f"API bağlantı hatası: {last_exc}")


# --- Gemini Yanıtı ---
def get_gemma_response(prompt_text):
    if prompt_text in gemma_cache:
        return gemma_cache[prompt_text]

    payload = {
        "contents": [
            {"parts": [{"text": prompt_text}]}
        ]
    }

    data = safe_request(payload)
    try:
        candidates = data.get("candidates", [])
        if candidates and isinstance(candidates, list):
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts and isinstance(parts, list):
                text = parts[0].get("text", "")
            else:
                text = ""
        else:
            text = data.get("output", {}).get("text", "") if isinstance(data, dict) else ""
    except Exception as e:
        app.logger.error(f"Parsing error: {e}\n{traceback.format_exc()}")
        text = "⚠️ Boş veya hatalı yanıt."

    text = text or "⚠️ Boş veya hatalı yanıt."
    gemma_cache[prompt_text] = text
    return text


# --- AFK Warmup ---
def afk_warmup():
    warmup_interval = 120
    warmup_messages = ["Merhaba!", "Nasılsın?"]
    while True:
        time.sleep(warmup_interval)
        idle_time = time.time() - AFK_MODE["last_active"]
        if idle_time > 60:
            app.logger.info("AFK warmup triggered")
            AFK_MODE["active"] = True
            try:
                for msg in warmup_messages:
                    executor.submit(get_gemma_response, msg)
                AFK_MODE["speed_multiplier"] = 0.8
            except Exception as e:
                app.logger.error(f"AFK warmup error: {e}")
        else:
            AFK_MODE["active"] = False
            AFK_MODE["speed_multiplier"] = 1.0


threading.Thread(target=afk_warmup, daemon=True).start()


# --- Health endpoint ---
@app.route("/health", methods=["GET"])
def health():
    ok = bool(GEMINI_API_KEY)
    return jsonify({"ok": ok, "key_present": ok}), (200 if ok else 503)


# --- Ana API route ---
@app.route("/gemma", methods=["POST"])
def gemma():
    try:
        req_json = request.get_json(force=True)
    except Exception:
        return jsonify({"response": "Geçersiz JSON"}), 400

    user_id = req_json.get("userId", "default")
    user_mesaj = req_json.get("message", "")
    user_info = req_json.get("userInfo", {})

    if not user_mesaj:
        return jsonify({"response": "Mesaj boş"}), 400

    AFK_MODE["last_active"] = time.time()

    if user_id not in user_memory:
        load_user_memory(user_id)

    user_memory[user_id]["conversation"].append({"role": "user", "text": user_mesaj})
    user_memory[user_id]["info"].update(user_info or {})

    try:
        memory_context = json.dumps(user_memory[user_id], ensure_ascii=False)
    except Exception:
        memory_context = "[]"

    prompt = (
        f"Kullanıcıyla geçmiş konuşmalar: {memory_context}\n"
        f"Kullanıcı yeni mesajı: {user_mesaj}\n"
        "Bu bilgilere dayanarak kişisel ve ilgili bir yanıt üret ve cevabı Türkçe ver."
    )

    try:
        text = get_gemma_response(prompt)
        user_memory[user_id]["conversation"].append({"role": "nova", "text": text})
        try:
            save_user_memory(user_id)
        except Exception as e:
            app.logger.error(f"save_user_memory failed: {e}")
        return jsonify({"response": text})
    except Exception as e:
        app.logger.error(f"gemma route error: {e}\n{traceback.format_exc()}")
        return jsonify({"response": f"⚠️ Hata: {e}"}), 500


# --- Sunucu Başlat ---
if __name__ == "__main__":
    from gevent.pywsgi import WSGIServer
    port = int(os.environ.get("PORT", 5000))
    app.logger.info(f"🚀 Nova backend {port} portunda çalışıyor...")
    http_server = WSGIServer(('0.0.0.0', port), app)
    http_server.serve_forever()
