from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
app = Flask(__name__)
CORS(app)  # Her yerden fetch yapılabilir
gemma_cache = {}

GEMINI_API_KEY = "AIzaSyBqWOT3n3LA8hJBriMGFFrmanLfkIEjhr0"
MODEL_NAME = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

@app.route("/gemma", methods=["POST"])
def gemma():
    user_mesaj = request.json.get("message", "")
    if not user_mesaj:
        return jsonify({"response": "Mesaj boş"}), 400

    if user_mesaj in gemma_cache:
        return jsonify({"response": gemma_cache[user_mesaj]})

    payload = {"contents":[{"parts":[{"text":user_mesaj}]}]}
    headers = {"Content-Type":"application/json", "x-goog-api-key": GEMINI_API_KEY}

    try:
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return jsonify({"response":"⚠️ Gemma yanıt vermedi (candidates boş)."})
        content_parts = candidates[0].get("content", {}).get("parts", [])
        text = content_parts[0].get("text", "") if content_parts else ""
        gemma_cache[user_mesaj] = text or "⚠️ Yanıt boş."
        return jsonify({"response": gemma_cache[user_mesaj]})
    except Exception as e:
        return jsonify({"response": f"⚠️ Hata: {e}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

