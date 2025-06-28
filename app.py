import os
from flask import Flask, request, jsonify, render_template
from google.generativeai import configure, GenerativeModel
from gtts import gTTS
import io
import base64
import traceback # ★ここを追加：tracebackモジュールをインポート

app = Flask(__name__)

# --- Gemini APIの設定 ---
# 環境変数からAPIキーを読み込む
# Renderにデプロイする際は、RenderのEnvironment VariablesでGEMINI_API_KEYを設定してください。
# ローカルで試す場合は、.envファイル（例: .env.exampleをコピーして作成）に記述するか、
# 環境変数として直接設定することもできます。
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY環境変数が設定されていません。AI応答機能が動作しない可能性があります。")
    # デバッグ用に、APIキーが読み込まれていないことをさらに明確にログ出力
    print("DEBUG: GEMINI_API_KEY is not set (from os.environ.get).")
else:
    print("DEBUG: GEMINI_API_KEY loaded successfully.") # ★ここを追加：APIキーが読み込まれたことをログ出力
    # print(f"DEBUG: Loaded API Key starts with: {GEMINI_API_KEY[:5]}...") # キーの冒頭をログに出すのはセキュリティリスクがあるので注意

# ここが重要です！configure関数でAPIキーを設定します。
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
        return jsonify({"error": "No text provided"}), 400

    # APIキーが設定されていない場合のチェックをここでも行い、より具体的なエラーメッセージを返す
    if not GEMINI_API_KEY:
        print("ERROR: API Key is missing for Gemini API call.") # ログにも出力
        return jsonify({"error": "Gemini API Key is not set. Please configure it in Render Environment Variables."}), 500

    try:
        # 会話履歴にユーザーの発言を追加
        # これはグローバル変数なので、実際のアプリではセッション管理が必要です
        conversation_history.append({"role": "user", "parts": [user_text]})
        
        # Geminiに質問を送信
        # generate_contentメソッドにconversation_historyを渡して会話の継続性を保つ
        response = model.generate_content(conversation_history)
        gemini_response_text = response.text
        
        # Geminiの応答を会話履歴に追加
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
            print(f"DEBUG: Successfully generated audio for text: {gemini_response_text[:50]}...") # ログ出力
            print(f"DEBUG: Audio Base64 length: {len(audio_base64)}") # 長さも出力
            
        except Exception as tts_e:
            print(f"ERROR: gTTS audio generation failed: {tts_e}")
            traceback.print_exc() # ★ここを追加：gTTSエラーのフルトレースバックを出力
            audio_base64 = "" 

        return jsonify({
            "response_text": gemini_response_text,
            "audio_base64": audio_base64
        })

    except Exception as e:
        print(f"ERROR: General error in ask_gemini: {e}")
        traceback.print_exc() # ★ここを追加：一般的なエラーのフルトレースバックを出力
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Render環境で実行されている場合、Renderが指定するポートを使用
    # ローカル開発時はデフォルトの5000ポートを使用
    port = int(os.environ.get('PORT', 5000))
    # Flaskアプリをすべてのネットワークインターフェース (0.0.0.0) で実行
    app.run(host='0.0.0.0', port=port, debug=True) # debug=Trueは開発用。本番ではFalseを推奨
