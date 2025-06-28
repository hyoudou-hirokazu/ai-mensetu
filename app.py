import os
from flask import Flask, request, jsonify, render_template
from google.generativeai import configure, GenerativeModel
from gtts import gTTS
import io
import base64
import traceback
import logging
import time # ★timeモジュールを追加

# ロガーの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Gemini APIの設定 ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY環境変数が設定されていません。AI応答機能が動作しない可能性があります。")
else:
    logger.debug("DEBUG: GEMINI_API_KEY loaded successfully.")
    
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
        logger.warning("No text provided in the request.")
        return jsonify({"error": "No text provided"}), 400

    if not GEMINI_API_KEY:
        logger.error("API Key is missing for Gemini API call.")
        return jsonify({"error": "Gemini API Key is not set. Please configure it in Render Environment Variables."}), 500

    try:
        conversation_history.append({"role": "user", "parts": [user_text]})
        
        response = model.generate_content(conversation_history)
        gemini_response_text = response.text
        
        conversation_history.append({"role": "model", "parts": [gemini_response_text]})

        audio_base64 = ""
        max_retries = 3 # ★リトライ回数を設定
        
        for attempt in range(max_retries): # ★リトライループを追加
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries}: Generating gTTS audio for text: {gemini_response_text[:50]}...")
                tts = gTTS(text=gemini_response_text, lang='ja', slow=False) 
                audio_buffer = io.BytesIO()
                tts.save(audio_buffer)
                audio_buffer.seek(0)

                audio_base64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
                
                if audio_base64: # Base64データが空でなければ成功とみなす
                    logger.debug(f"Successfully generated audio for text: {gemini_response_text[:50]}...")
                    logger.debug(f"Audio Base64 length: {len(audio_base64)}")
                    break # 成功したのでループを抜ける
                else:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries}: gTTS generated empty audio_base64. Retrying...")
                    time.sleep(1) # 1秒待ってから再試行

            except Exception as tts_e:
                logger.error(f"Attempt {attempt + 1}/{max_retries}: gTTS audio generation failed: {tts_e}")
                logger.error(traceback.format_exc())
                audio_base64 = "" # 失敗時は空のまま
                if attempt < max_retries - 1:
                    time.sleep(1) # 再試行前に少し待つ
                else:
                    logger.error("All gTTS retries failed.") # 全てのリトライが失敗したことをログに記録

        return jsonify({
            "response_text": gemini_response_text,
            "audio_base64": audio_base64
        })

    except Exception as e:
        logger.error(f"General error in ask_gemini: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
