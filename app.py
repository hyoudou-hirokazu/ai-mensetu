# app.py

import os
from flask import Flask, request, jsonify, render_template_string
from google.cloud import speech_v1p1beta1 as speech
import google.generativeai as genai
from gtts import gTTS
import base64
import io
import time

app = Flask(__name__)

# Google Cloud プロジェクトIDの設定 (環境変数から取得、または直接記述)
# 環境変数で設定することを推奨: export GOOGLE_CLOUD_PROJECT="your-project-id"
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id") # 'your-gcp-project-id' を実際のプロジェクトIDに置き換えてください

# Gemini APIの初期設定
# 環境変数 GOOGLE_API_KEY または GOOGLE_APPLICATION_CREDENTIALS が設定されていれば自動で認証されます
# ローカル開発では GOOGLE_APPLICATION_CREDENTIALS を推奨
genai.configure()

# Geminiモデルの選択
# Flashモデルを使用します。
GEMINI_MODEL_FLASH = "gemini-1.5-flash-latest"

# ----- グローバル変数またはセッション管理で面接履歴を保持 -----
# 本来はユーザーセッションごとに管理すべきですが、今回は簡単な例としてグローバル変数で管理
# 実際のアプリケーションでは、ユーザーIDとセッションIDに基づいてデータベースやキャッシュで管理します
interview_history = []
interview_type = None # 'general' or 'disability'

# ----- Flaskのエンドポイント設定 -----

# フロントエンドのHTMLを提供するルート
@app.route('/')
def index():
    # ここにHTMLコンテンツを直接記述するか、templateファイル（templates/index.html）を読み込む
    # まずはシンプルなHTMLで動作確認
    html_content = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI 面接練習</title>
        <style>
            body { font-family: sans-serif; margin: 20px; }
            #controls button { margin: 5px; padding: 10px 20px; font-size: 16px; }
            #output { margin-top: 20px; padding: 15px; border: 1px solid #ccc; background-color: #f9f9f9; min-height: 100px; }
            #feedback { margin-top: 20px; padding: 15px; border: 1px solid #cceeff; background-color: #e6f7ff; min-height: 50px; }
            .message { margin-bottom: 10px; }
            .ai-message { color: blue; }
            .user-message { color: green; }
            .thinking { font-style: italic; color: gray; }
        </style>
    </head>
    <body>
        <h1>AI 面接練習アプリ</h1>

        <div>
            <label for="interviewType">面接タイプを選択:</label>
            <select id="interviewType">
                <option value="general">一般企業向け</option>
                <option value="disability">障害者雇用向け（合理的配慮あり）</option>
            </select>
            <button id="startButton">面接開始</button>
        </div>

        <div id="controls" style="margin-top: 20px;">
            <button id="recordButton">録音開始</button>
            <button id="stopButton" disabled>録音停止</button>
            <button id="resetButton">リセット</button>
        </div>

        <div id="status" style="margin-top: 10px; color: gray;">ステータス: 準備完了</div>
        <div id="output"></div>
        <div id="feedback"></div>

        <audio id="audioPlayback" controls style="display: none;"></audio>

        <script>
            let mediaRecorder;
            let audioChunks = [];
            let interviewStarted = false;

            const recordButton = document.getElementById('recordButton');
            const stopButton = document.getElementById('stopButton');
            const startButton = document.getElementById('startButton');
            const resetButton = document.getElementById('resetButton');
            const outputDiv = document.getElementById('output');
            const feedbackDiv = document.getElementById('feedback');
            const statusDiv = document.getElementById('status');
            const audioPlayback = document.getElementById('audioPlayback');
            const interviewTypeSelect = document.getElementById('interviewType');

            // --- 音声認識（録音）と再生の関数 ---
            recordButton.onclick = async () => {
                if (!interviewStarted) {
                    alert('面接を開始してください。');
                    return;
                }
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];

                    mediaRecorder.ondataavailable = event => {
                        audioChunks.push(event.data);
                    };

                    mediaRecorder.onstop = async () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                        const reader = new FileReader();
                        reader.readAsDataURL(audioBlob);
                        reader.onloadend = () => {
                            const base64data = reader.result.split(',')[1];
                            sendAudioToServer(base64data);
                        };
                    };

                    mediaRecorder.start();
                    statusDiv.textContent = 'ステータス: 録音中...';
                    recordButton.disabled = true;
                    stopButton.disabled = false;
                } catch (error) {
                    console.error('マイクアクセスエラー:', error);
                    statusDiv.textContent = 'ステータス: マイクアクセスに失敗しました。';
                    alert('マイクへのアクセスを許可してください。');
                }
            };

            stopButton.onclick = () => {
                mediaRecorder.stop();
                statusDiv.textContent = 'ステータス: 録音停止。AIが応答中...';
                recordButton.disabled = true;
                stopButton.disabled = true;
                outputDiv.innerHTML += '<div class="message user-message">あなた: (録音中...)</div>';
            };

            async function playAudio(base64Audio) {
                const audioBlob = await fetch(`data:audio/mp3;base64,${base64Audio}`).then(res => res.blob());
                const audioUrl = URL.createObjectURL(audioBlob);
                audioPlayback.src = audioUrl;
                audioPlayback.load();
                audioPlayback.play();
                audioPlayback.onended = () => {
                    statusDiv.textContent = 'ステータス: 準備完了。録音を開始できます。';
                    recordButton.disabled = false;
                };
            }

            // --- Flaskバックエンドとの通信 ---
            async function sendAudioToServer(base64Audio) {
                try {
                    const response = await fetch('/interview', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ audio_data: base64Audio }),
                    });

                    const data = await response.json();
                    if (response.ok) {
                        outputDiv.innerHTML += `<div class="message ai-message">面接官: ${data.ai_response_text}</div>`;
                        feedbackDiv.innerHTML = `<div class="message">フィードバック: ${data.feedback_text}</div>`;
                        await playAudio(data.ai_response_audio);
                    } else {
                        outputDiv.innerHTML += `<div class="message" style="color: red;">エラー: ${data.error}</div>`;
                        statusDiv.textContent = 'ステータス: エラーが発生しました。';
                        recordButton.disabled = false; // エラー時は録音再開可能に
                    }
                } catch (error) {
                    console.error('サーバー通信エラー:', error);
                    outputDiv.innerHTML += `<div class="message" style="color: red;">通信エラー: ${error.message}</div>`;
                    statusDiv.textContent = 'ステータス: 通信エラーが発生しました。';
                    recordButton.disabled = false; // エラー時は録音再開可能に
                }
            }

            // --- 面接開始/リセット機能 ---
            startButton.onclick = async () => {
                interviewType = interviewTypeSelect.value;
                statusDiv.textContent = 'ステータス: 面接を開始します...';
                outputDiv.innerHTML = '';
                feedbackDiv.innerHTML = '';
                recordButton.disabled = true;
                stopButton.disabled = true;
                startButton.disabled = true;

                try {
                    const response = await fetch('/start_interview', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ interview_type: interviewType }),
                    });
                    const data = await response.json();
                    if (response.ok) {
                        outputDiv.innerHTML += `<div class="message ai-message">面接官: ${data.ai_response_text}</div>`;
                        await playAudio(data.ai_response_audio);
                        interviewStarted = true;
                        recordButton.disabled = false; // 最初の質問が来たら録音開始可能に
                        statusDiv.textContent = 'ステータス: 面接中。最初の質問が来ました。';
                    } else {
                        outputDiv.innerHTML += `<div class="message" style="color: red;">面接開始エラー: ${data.error}</div>`;
                        statusDiv.textContent = 'ステータス: 面接開始に失敗しました。';
                        startButton.disabled = false;
                    }
                } catch (error) {
                    console.error('面接開始通信エラー:', error);
                    outputDiv.innerHTML += `<div class="message" style="color: red;">面接開始通信エラー: ${error.message}</div>`;
                    statusDiv.textContent = 'ステータス: 面接開始通信エラー。';
                    startButton.disabled = false;
                }
            };

            resetButton.onclick = async () => {
                interviewStarted = false;
                outputDiv.innerHTML = '';
                feedbackDiv.innerHTML = '';
                statusDiv.textContent = 'ステータス: リセット完了。面接を開始してください。';
                recordButton.disabled = true;
                stopButton.disabled = true;
                startButton.disabled = false;
                await fetch('/reset_interview', { method: 'POST' }); // バックエンドもリセット
            };
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content)

# 面接開始時のエンドポイント
@app.route('/start_interview', methods=['POST'])
def start_interview():
    global interview_history, interview_type
    interview_history = [] # 履歴をリセット
    data = request.json
    interview_type = data.get('interview_type', 'general') # デフォルトは一般企業向け

    try:
        if interview_type == 'general':
            initial_prompt = "あなたは株式会社〇〇の面接官です。これから応募者に対して面接を行います。最初の質問をしてください。面接官として、常に丁寧な言葉遣いで、客観的かつ具体的に質問してください。フィードバックはまだ不要です。"
        else: # 'disability'
            initial_prompt = "あなたは株式会社〇〇の面接官です。障害者雇用枠の応募者に対して面接を行います。最初の質問をしてください。障害特性や合理的配慮について理解を示しつつ、丁寧な言葉遣いで、客観的かつ具体的に質問してください。フィードバックはまだ不要です。"

        model = genai.GenerativeModel(GEMINI_MODEL_FLASH)
        # 履歴をクリアした状態で最初の質問を生成
        response = model.generate_content(
            contents=[{"role": "user", "parts": [initial_prompt]}],
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        ai_response_text = response.candidates[0].content.parts[0].text

        # 履歴に追加
        interview_history.append({"role": "user", "parts": [initial_prompt]})
        interview_history.append({"role": "model", "parts": [ai_response_text]})

        # 音声合成
        tts = gTTS(text=ai_response_text, lang='ja', slow=True) # ゆっくり目の日本語音声
        audio_buffer = io.BytesIO()
        tts.save(audio_buffer)
        audio_buffer.seek(0)
        ai_response_audio_base64 = base64.b64encode(audio_buffer.read()).decode('utf-8')

        return jsonify({
            'ai_response_text': ai_response_text,
            'ai_response_audio': ai_response_audio_base64,
            'feedback_text': "面接が開始されました。最初の質問です。"
        })

    except Exception as e:
        app.logger.error(f"面接開始エラー: {e}", exc_info=True)
        return jsonify({'error': f'面接開始時にエラーが発生しました: {str(e)}'}), 500

# 面接リセット時のエンドポイント
@app.route('/reset_interview', methods=['POST'])
def reset_interview():
    global interview_history, interview_type
    interview_history = []
    interview_type = None
    return jsonify({'status': '面接履歴がリセットされました。'})


# 面接の質問と応答処理のエンドポイント
@app.route('/interview', methods=['POST'])
def interview_endpoint():
    data = request.json
    audio_data_base64 = data['audio_data']
    
    if not interview_history:
        return jsonify({'error': '面接が開始されていません。先に面接を開始してください。'}), 400

    try:
        # 1. 音声テキスト化 (Speech-to-Text)
        audio_content = base64.b64decode(audio_data_base64)
        
        speech_client = speech.SpeechClient()
        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS, # ブラウザからの録音形式
            sample_rate_hertz=48000, # ブラウザのデフォルトレートに合わせて調整
            language_code="ja-JP",
            model="default" # デフォルトモデルを使用
        )

        app.logger.info("Speech-to-Text APIにリクエストを送信中...")
        response = speech_client.recognize(config=config, audio=audio)
        user_response_text = ""
        if response.results:
            user_response_text = response.results[0].alternatives[0].transcript
            app.logger.info(f"ユーザーの回答: {user_response_text}")
        else:
            user_response_text = "（音声認識できませんでした）"
            app.logger.warning("Speech-to-Textで音声が認識できませんでした。")

        # 履歴に追加
        interview_history.append({"role": "user", "parts": [f"応募者: {user_response_text}"]})

        # 2. Gemini APIによる次の質問とフィードバックの生成
        model = genai.GenerativeModel(GEMINI_MODEL_FLASH)
        
        # 面接タイプに応じたプロンプト調整
        feedback_instruction = ""
        if interview_type == 'general':
            feedback_instruction = "この回答に対して、面接官として客観的かつ具体的にフィードバックを行ってください（文字数制限なし）。その上で、次の面接官としての質問を生成してください。質問は自然で、会話の流れに沿ったものにしてください。フィードバックと質問は必ず分けて提示し、それぞれの開始に`[フィードバック]`と`[質問]`というマーカーを付けてください。"
        else: # 'disability'
            feedback_instruction = "この回答に対して、面接官として障害特性と合理的配慮に配慮しつつ、客観的かつ具体的にフィードバックを行ってください（文字数制限なし）。その上で、次の面接官としての質問を生成してください。質問は、応募者の障害特性や合理的配慮への理解を示す形で、自然で会話の流れに沿ったものにしてください。フィードバックと質問は必ず分けて提示し、それぞれの開始に`[フィードバック]`と`[質問]`というマーカーを付けてください。"

        # 会話履歴をGeminiに渡して、文脈に応じた応答を生成
        # プロンプトの最後にフィードバックと次の質問の指示を追加
        current_conversation = interview_history + [{"role": "user", "parts": [feedback_instruction]}]

        app.logger.info("Gemini APIに質問とフィードバックのリクエストを送信中...")
        gemini_response = model.generate_content(
            contents=current_conversation,
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        ai_full_response_text = gemini_response.candidates[0].content.parts[0].text
        app.logger.info(f"Geminiからのフル応答: {ai_full_response_text}")

        # Geminiからの応答をフィードバックと次の質問に分割
        feedback_start_tag = "[フィードバック]"
        question_start_tag = "[質問]"
        
        feedback_text = "フィードバックを生成できませんでした。"
        ai_response_text = "次の質問を生成できませんでした。"

        if feedback_start_tag in ai_full_response_text and question_start_tag in ai_full_response_text:
            feedback_index = ai_full_response_text.find(feedback_start_tag)
            question_index = ai_full_response_text.find(question_start_tag)

            if feedback_index < question_index: # フィードバックが先にくる場合
                feedback_text = ai_full_response_text[feedback_index + len(feedback_start_tag):question_index].strip()
                ai_response_text = ai_full_response_text[question_index + len(question_start_tag):].strip()
            else: # 質問が先にくる、または順序が逆の場合も考慮
                # このケースは想定外だが、念のため両方のパターンをチェック
                feedback_text = "Geminiからの応答解析に失敗しました。フィードバックの開始タグが見つかりません。"
                ai_response_text = "Geminiからの応答解析に失敗しました。質問の開始タグが見つかりません。"
                app.logger.warning("Gemini応答のタグ解析順序が想定と異なりました。")
        else:
            # タグが見つからない場合、応答全体をフィードバックとして処理し、次の質問はなしとするか、デフォルトを返す
            feedback_text = ai_full_response_text # 全体をフィードバックとして表示
            ai_response_text = "（面接官：次の質問はありません。面接を終了します。）" # 質問がない場合のメッセージ
            app.logger.warning("Gemini応答でフィードバックまたは質問のタグが見つかりませんでした。")
            
        # 履歴に追加 (モデルからの応答は、次にユーザーの入力を促す質問のみを想定)
        interview_history.append({"role": "model", "parts": [ai_response_text]})


        # 3. 音声合成 (gTTS)
        tts = gTTS(text=ai_response_text, lang='ja', slow=True) # ゆっくり目の日本語音声
        audio_buffer = io.BytesIO()
        tts.save(audio_buffer)
        audio_buffer.seek(0)
        ai_response_audio_base64 = base64.b64encode(audio_buffer.read()).decode('utf-8')

        return jsonify({
            'user_response_text': user_response_text,
            'ai_response_text': ai_response_text,
            'feedback_text': feedback_text,
            'ai_response_audio': ai_response_audio_base64
        })

    except Exception as e:
        app.logger.error(f"面接処理中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({'error': f'面接処理中にエラーが発生しました: {str(e)}'}), 500


# アプリケーションの実行
if __name__ == '__main__':
    # Flaskのデバッグモードは開発時に便利ですが、本番環境では無効にしてください
    # app.run(debug=True, port=8080)
    # Cloud Runは環境変数PORTを使用するため、本番環境では以下のようになります
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 8080))
