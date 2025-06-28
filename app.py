import os
from flask import Flask, request, jsonify, render_template
from google.generativeai import configure, GenerativeModel
from gtts import gTTS
import io
import base64
import traceback
import logging # ★ここを追加

# ロガーの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # ★ここを追加

app = Flask(__name__)

# ... (Gemini APIの設定部分は変更なし) ...
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY環境変数が設定されていません。AI応答機能が動作しない可能性があります。") # ★loggingを使用
    logger.debug("GEMINI_API_KEY is not set (from os.environ.get).") # ★loggingを使用
else:
    logger.debug("GEMINI_API_KEY loaded successfully.") # ★loggingを使用

configure(api_key=GEMINI_API_KEY)

model = GenerativeModel('gemini-2.5-flash')
conversation_history = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask_gemini():
    data = request.json
    user_text = data.get('text')

    if not user_text:
        return jsonify({"error": "No text provided"}), 400

    if not GEMINI_API_KEY:
        logger.error("API Key is missing for Gemini API call.") # ★loggingを使用
        return jsonify({"error": "Gemini API Key is not set. Please configure it in Render Environment Variables."}), 500

    try:
        conversation_history.append({"role": "user", "parts": [user_text]})

        response = model.generate_content(conversation_history)
        gemini_response_text = response.text

        conversation_history.append({"role": "model", "parts": [gemini_response_text]})

        audio_base64 = ""

        try:
            # gTTSで日本語音声を生成 (timeout=10, slow=False を追加)
            tts = gTTS(text=gemini_response_text, lang='ja', slow=False, timeout=10)
            audio_buffer = io.BytesIO()
            tts.save(audio_buffer)
            audio_buffer.seek(0)

            audio_base64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
            logger.debug(f"Successfully generated audio for text: {gemini_response_text[:50]}...") # ★loggingを使用
            logger.debug(f"Audio Base64 length: {len(audio_base64)}") # ★loggingを使用

        except Exception as tts_e:
            logger.error(f"gTTS audio generation failed: {tts_e}") # ★loggingを使用
            logger.error(traceback.format_exc()) # ★ここを修正：トレースバック全体をログに出力
            audio_base64 = "" 

        return jsonify({
            "response_text": gemini_response_text,
            "audio_base64": audio_base64
        })

    except Exception as e:
        logger.error(f"General error in ask_gemini: {e}") # ★loggingを使用
        logger.error(traceback.format_exc()) # ★ここを修正：トレースバック全体をログに出力
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
