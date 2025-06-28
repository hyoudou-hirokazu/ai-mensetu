import os
from flask import Flask, request, jsonify, render_template
from google.generativeai import configure, GenerativeModel
from gtts import gTTS
import io
import base64

app = Flask(__name__)

# --- Gemini APIの設定 ---
# 環境変数からAPIキーを読み込む
# Renderにデプロイする際は、RenderのEnvironment VariablesでGEMINI_API_KEYを設定してください。
# ローカルで試す場合は、.envファイル（例: .env.exampleをコピーして作成）に記述するか、
# 直接ここにAPIキーを書く（非推奨）こともできます。
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY環境変数が設定されていません。")

configure(api_key=GEMINI_API_KEY)
model = GenerativeModel('gemini-pro')

# Geminiとの会話履歴を保持するためのリスト
# 実際にはセッション管理やデータベースを使用すべきですが、今回は簡易化のためグローバル変数で保持します。
# 複数のユーザーが同時にアクセスする場合、この方法は適切ではありません。
# その場合は、ユーザーごとにセッションIDなどを割り当てて管理する必要があります。
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

    try:
        # Geminiへのプロンプト
        # 面接官として振る舞うよう指示
        prompt_parts = [
            "あなたは日本語の就労支援面接官です。以下にユーザーが返答するので、面接の質問をしてください。",
            "ユーザー: " + user_text,
            "面接官: " # ここにGeminiの応答が入る
        ]
        
        # 会話履歴を追加
        conversation_history.append({"role": "user", "parts": [user_text]})
        
        # Geminiに質問を送信
        # generate_contentメソッドにconversation_historyを渡して会話の継続性を保つ
        response = model.generate_content(conversation_history)
        gemini_response_text = response.text
        
        # Geminiの応答を会話履歴に追加
        conversation_history.append({"role": "model", "parts": [gemini_response_text]})

        # gTTSで日本語音声を生成
        tts = gTTS(text=gemini_response_text, lang='ja')
        audio_buffer = io.BytesIO()
        tts.save(audio_buffer)
        audio_buffer.seek(0) # バッファの先頭に戻す

        # 音声データをBase64エンコードしてJSONで返す
        audio_base64 = base64.b64encode(audio_buffer.read()).decode('utf-8')
        
        return jsonify({
            "response_text": gemini_response_text,
            "audio_base64": audio_base64
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True) # ローカル開発時はdebug=Trueでホットリロード有効