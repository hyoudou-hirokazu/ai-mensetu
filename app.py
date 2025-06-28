import os
from flask import Flask, request, jsonify, render_template
from google.generativeai import configure, GenerativeModel
from gtts import gTTS
import io
import base64
import traceback # これを追加

app = Flask(__name__)

# --- Gemini APIの設定 ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY環境変数が設定されていません。AI応答機能が動作しない可能性があります。")

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
        return jsonify({"error": "Gemini API Key is not set. Please configure it in Render Environment Variables."}), 500

    try:
        conversation_history.append({"role": "user", "parts": [user_text]})

        response = model.generate_content(conversation_history)
        gemini_response_text = response.text

        conversation_history.append({"role": "model", "parts": [gemini_response_text]})

        audio_base64 = "" # gTTSの生成結果を保持する変数を初期化

        try:
            # gTTSで日本語音声を生成
            tts = gTTS(text=gemini_response_text, lang='ja')
            audio_buffer = io.BytesIO()
            tts.save(audio_buffer)
            audio_buffer.seek(0) # バッファの先頭に戻す

            # 音声データをBase64エンコード
            audio_base64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
            print(f"DEBUG: Successfully generated audio for text: {gemini_response_text[:50]}...")
            print(f"DEBUG: Audio Base64 length: {len(audio_base64)}")

        except Exception as tts_e:
            print(f"ERROR: gTTS audio generation failed: {tts_e}")
            # トレースバックも出力
            traceback.print_exc() # これを追加
            audio_base64 = "" 

        return jsonify({
            "response_text": gemini_response_text,
            "audio_base64": audio_base64
        })

    except Exception as e:
        print(f"ERROR: General error in ask_gemini: {e}")
        # トレースバックも出力
        traceback.print_exc() # これを追加
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
