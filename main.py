import os
from flask import Flask, request, jsonify, render_template
from google.generativeai import configure, GenerativeModel
from gtts import gTTS
import io
import base64
import traceback
import logging
import time # timeモジュールを追加

# ロガーの設定
# Renderのログに出力されるように、INFOレベル以上で設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Gemini APIの設定 ---
# 環境変数からAPIキーを読み込む
# Renderにデプロイする際は、RenderのEnvironment VariablesでGEMINI_API_KEYを設定してください。
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY環境変数が設定されていません。AI応答機能が動作しない可能性があります。")
    logger.debug("DEBUG: GEMINI_API_KEY is not set (from os.environ.get).")
else:
    logger.debug("DEBUG: GEMINI_API_KEY loaded successfully.")
    
# ここが重要です！configure関数でAPIキーを設定します。
# APIキーがNoneの場合でもconfigureは呼ばれますが、Gemini API呼び出し時にエラーとなるため、
# その前のif not GEMINI_API_KEY: で早期終了するようにしています。
configure(api_key=GEMINI_API_KEY)

# Geminiモデルの指定
model = GenerativeModel('gemini-2.5-flash')

# Geminiとの会話履歴を保持するためのリスト
# 注意: これは簡易的な実装であり、複数のユーザーが同時にアクセスする場合、会話が混ざります。
# 実際にはFlaskのセッション管理やデータベースを使用すべきです。
conversation_history = []

# --- Flaskルート設定 ---

@app.route('/')
def index():
    """
    アプリケーションのトップページを表示します。
    """
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask_gemini():
    """
    ユーザーからのテキストを受け取り、Geminiに質問し、
    その応答を音声ファイルとして返します。
    """
    data = request.json
    user_text = data.get('text')

    if not user_text:
        logger.warning("No text provided in the request.")
        return jsonify({"error": "No text provided"}), 400

    # APIキーが設定されていない場合のチェックをここでも行い、より具体的なエラーメッセージを返す
    if not GEMINI_API_KEY:
        logger.error("API Key is missing for Gemini API call.")
        return jsonify({"error": "Gemini API Key is not set. Please configure it in Render Environment Variables."}), 500

    try:
        # 会話履歴にユーザーの発言を追加
        conversation_history.append({"role": "user", "parts": [user_text]})
        
        # Geminiに質問を送信
        response = model.generate_content(conversation_history)
        gemini_response_text = response.text
        
        # Geminiの応答を会話履歴に追加
        conversation_history.append({"role": "model", "parts": [gemini_response_text]})

        audio_base64 = "" # gTTSの生成結果を保持する変数を初期化
        max_retries = 3 # リトライ回数を設定
        
        for attempt in range(max_retries): # リトライループを追加
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries}: Generating gTTS audio for text: {gemini_response_text[:50]}...")
                # gTTSで日本語音声を生成
                # TypeErrorの原因だった 'timeout' 引数を削除済み
                tts = gTTS(text=gemini_response_text, lang='ja', slow=False) 
                audio_buffer = io.BytesIO()
                tts.save(audio_buffer)
                audio_buffer.seek(0)

                # 音声データをBase64エンコード
                audio_base64 = base64.b64encode(audio_buffer.read()).decode('utf-8')

