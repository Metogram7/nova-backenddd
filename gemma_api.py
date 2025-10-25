from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, time, requests

app = Flask(__name__)
CORS(app)

# --- Ayarlar ---
DATA_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(DATA_DIR, exist_ok=True)

user_memory = {}

GEMINI_API_KEY = "AIzaSyBqWOT3n3LA8hJBriMGFFrmanLfkIEjhr0"
MODEL_NAME = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

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

@app.route("/nova", methods=["POST"])
def nova():
    req = request.json
    user_id = req.get("userId", "default")
    message = req.get("message", "")
    user_info = req.get("userInfo", {})

    if not message:
        return jsonify({"response": "Mesaj boş"}), 400

    if user_id not in user_memory:
        load_user_memory(user_id)

    # Hafızaya kaydet
    user_memory[user_id]["conversation"].append({"role":"user","text":message})
    user_memory[user_id]["info"].update(user_info)

    # Gemini API çağrısı
    prompt = {
        "contents": [
            {"parts":[{"text":f"Kullanıcı bilgileri: {json.dumps(user_memory[user_id])}\nYeni mesaj: {message}\nTürkçe yanıt ver."}]} 
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    try:
        resp = requests.post(GEMINI_API_URL, json=prompt, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        reply = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "⚠️ Yanıt boş.")
    except Exception as e:
        reply = f"⚠️ API Hatası: {e}"

    # Hafızaya kaydet
    user_memory[user_id]["conversation"].append({"role":"nova","text":reply})
    save_user_memory(user_id)

    return jsonify({"response": reply})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Nova backend {port} portunda çalışıyor...")
    app.run(host="0.0.0.0", port=port)
