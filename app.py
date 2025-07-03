# app.py

import os
from flask import Flask, request, jsonify, render_template_string
from google.cloud import speech_v1p1beta1 as speech
import google.generativeai as genai
from gtts import gTTS
import base64
import io
import time
import logging # ロギングを追加

# ロギング設定
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# Google Cloud プロジェクトIDの設定 (環境変数から取得、または直接記述)
# Cloud Runでは、デフォルトのサービスアカウントが使用されるため、
# GOOGLE_APPLICATION_CREDENTIALS はローカル開発用です。
# PROJECT_IDは不要な場合が多いですが、明示的に設定するなら環境変数から取得します。
# 例: export GOOGLE_CLOUD_PROJECT="your-project-id"
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id") # 'your-gcp-project-id' を実際のプロジェクトIDに置き換えてください

# Gemini APIの初期設定
# Cloud Runでは、インスタンスに割り当てられたサービスアカウントが自動的に認証に使用されます
genai.configure()

# Geminiモデルの選択
GEMINI_MODEL_FLASH = "gemini-1.5-flash-latest"

# ----- グローバル変数で面接履歴と面接タイプを保持 -----
# 注意: 実際のアプリケーションでは、ユーザーセッションごとにこれらの情報を安全に管理する必要があります。
# （例: データベース、Redisキャッシュ、またはセッション管理ライブラリなど）
# グローバル変数は、単一ユーザーでのテストやプロトタイプにのみ適しています。
interview_history = []
interview_type = None # 'general' or 'disability'

# ----- Flaskのエンドポイント設定 -----

# フロントエンドのHTMLを提供するルート
@app.route('/')
def index():
    html_content = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI 面接練習</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f0f2f5; color: #333; }
            h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
            .container { max-width: 800px; margin: 0 auto; background-color: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1); }
            .controls-group { display: flex; justify-content: center; align-items: center; gap: 15px; margin-bottom: 25px; }
            .controls-group label, .controls-group select { font-size: 16px; }
            .controls-group button {
                padding: 12px 25px;
                font-size: 16px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                transition: background-color 0.3s ease, transform 0.2s ease;
                color: #fff;
            }
            #startButton { background-color: #28a745; }
            #startButton:hover { background-color: #218838; transform: translateY(-2px); }
            #recordButton { background-color: #007bff; }
            #recordButton:hover { background-color: #0056b3; transform: translateY(-2px); }
            #stopButton { background-color: #dc3545; }
            #stopButton:hover { background-color: #c82333; transform: translateY(-2px); }
            #resetButton { background-color: #6c757d; }
            #resetButton:hover { background-color: #5a6268; transform: translateY(-2px); }
            #recordButton:disabled, #stopButton:disabled, #startButton:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }
            #status { margin-top: 15px; text-align: center; font-weight: bold; color: #6c757d; }
            #output {
                margin-top: 25px;
                padding: 20px;
                border: 1px solid #e0e0e0;
                background-color: #fafafa;
                min-height: 200px;
                max-height: 400px;
                overflow-y: auto;
                border-radius: 8px;
            }
            #feedback {
                margin-top: 20px;
                padding: 20px;
                border: 1px solid #b3e0ff;
                background-color: #e6f7ff;
                min-height: 80px;
                border-radius: 8px;
            }
            .message { margin-bottom: 12px; line-height: 1.6; }
            .ai-message { color: #0056b3; font-weight: bold; }
            .user-message { color: #28a745; }
            .thinking { font-style: italic; color: #999; }
            #audioPlayback { display: none; } /* デバッグ時以外は非表示 */
        </style>
    </head>
    <body>
        <div class="container">
            <h1>AI 面接練習アプリ</h1>

            <div class="controls-group">
                <label for="interviewType">面接タイプを選択:</label>
                <select id="interviewType">
                    <option value="general">一般企業向け</option>
                    <option value="disability">障害者雇用向け（合理的配慮あり）</option>
                </select>
                <button id="startButton">面接開始</button>
            </div>

            <div class="controls-group">
                <button id="recordButton" disabled>録音開始</button>
                <button id="stopButton" disabled>録音停止</button>
                <button id="resetButton">リセット</button>
            </div>

            <div id="status">ステータス: 準備完了</div>
            <div id="output"></div>
            <div id="feedback"></div>

            <audio id="audioPlayback" controls style="display: none;"></audio>

        </div> <script>
            let mediaRecorder;
            let audioChunks = [];
            let interviewStarted = false;
            let audioContext = null; // AudioContext for better audio handling

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
                statusDiv.textContent = 'ステータス: マイクへのアクセスを要求中...';
                try {
                    // AudioContextの初期化（一度だけ）
                    if (!audioContext) {
                        audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    }

                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' }); // opus codecを明示
                    audioChunks = [];

                    mediaRecorder.ondataavailable = event => {
                        audioChunks.push(event.data);
                    };

                    mediaRecorder.onstop = async () => {
                        statusDiv.textContent = 'ステータス: 録音停止。AIが応答中...';
                        recordButton.disabled = true; // 録音停止後は無効化
                        stopButton.disabled = true;

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
                    statusDiv.textContent = 'ステータス: マイクアクセスに失敗しました。マイクを許可してください。';
                    alert('マイクへのアクセスを許可してください。');
                    recordButton.disabled = false; // エラー時は録音再開可能に
                    stopButton.disabled = true;
                }
            };

            stopButton.onclick = () => {
                if (mediaRecorder && mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                    // mediaRecorder.onstop でステータスとボタンが更新される
                }
            };

            // 音声再生関数
            async function playAudio(base64Audio) {
                try {
                    const audioBlob = await fetch(`data:audio/mp3;base64,${base64Audio}`).then(res => res.blob());
                    const audioUrl = URL.createObjectURL(audioBlob);
                    audioPlayback.src = audioUrl;
                    audioPlayback.load(); // 音源をロード

                    // 音声再生が始まる前に、一旦ボタンを有効に戻す
                    // これで、音声再生に失敗しても次の録音に進めるようになります
                    statusDiv.textContent = 'ステータス: AIが応答中... (再生待ち)';
                    recordButton.disabled = false; // ここで録音ボタンを有効に戻す！

                    // 音声再生を開始
                    // Promiseを返すので、再生完了やエラーを待つことができる
                    await audioPlayback.play();
                    console.log('Audio playback started.'); // デバッグ用

                    // 再生が完了したらステータスを更新
                    statusDiv.textContent = 'ステータス: 準備完了。録音を開始できます。';
                    recordButton.disabled = false; // 再度有効化（念のため）

                } catch (error) {
                    console.error('音声再生エラー:', error);
                    statusDiv.textContent = 'ステータス: 音声再生エラー。手動で録音開始ボタンを押してください。';
                    recordButton.disabled = false; // エラーでも有効に
                    // alert('音声の再生中にエラーが発生しました。ブラウザのコンソールを確認してください。');
                }
            }


            // --- Flaskバックエンドとの通信 ---
            async function sendAudioToServer(base64Audio) {
                try {
                    outputDiv.innerHTML += '<div class="message user-message">あなた: <span class="thinking">(テキスト変換中...)</span></div>';
                    const response = await fetch('/interview', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ audio_data: base64Audio }),
                    });

                    const data = await response.json();
                    
                    // ユーザーの回答テキストを更新
                    const lastUserMessage = outputDiv.querySelector('.user-message:last-child');
                    if (lastUserMessage && data.user_response_text) {
                        lastUserMessage.innerHTML = `あなた: ${data.user_response_text}`;
                    } else if (data.user_response_text) {
                        outputDiv.innerHTML += `<div class="message user-message">あなた: ${data.user_response_text}</div>`;
                    }
                    outputDiv.scrollTop = outputDiv.scrollHeight; // スクロール

                    if (response.ok) {
                        outputDiv.innerHTML += `<div class="message ai-message">面接官: ${data.ai_response_text}</div>`;
                        feedbackDiv.innerHTML = `<div class="message">フィードバック: ${data.feedback_text}</div>`;
                        outputDiv.scrollTop = outputDiv.scrollHeight; // スクロール

                        await playAudio(data.ai_response_audio); // 音声再生が完了するまで待機
                        // playAudio内でボタン再有効化とステータス更新が行われる
                    } else {
                        outputDiv.innerHTML += `<div class="message" style="color: red;">エラー: ${data.error}</div>`;
                        statusDiv.textContent = 'ステータス: エラーが発生しました。';
                        recordButton.disabled = false; // エラー時は録音再開可能に
                        outputDiv.scrollTop = outputDiv.scrollHeight; // スクロール
                    }
                } catch (error) {
                    console.error('サーバー通信エラー:', error);
                    outputDiv.innerHTML += `<div class="message" style="color: red;">通信エラー: ${error.message}</div>`;
                    statusDiv.textContent = 'ステータス: 通信エラーが発生しました。';
                    recordButton.disabled = false; // エラー時は録音再開可能に
                    outputDiv.scrollTop = outputDiv.scrollHeight; // スクロール
                }
            }

            // --- 面接開始/リセット機能 ---
            startButton.onclick = async () => {
                if (interviewStarted) {
                    alert('面接はすでに開始されています。リセットする場合は「リセット」ボタンを押してください。');
                    return;
                }
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
                        outputDiv.scrollTop = outputDiv.scrollHeight; // スクロール
                        await playAudio(data.ai_response_audio); // 最初の質問を再生
                        interviewStarted = true;
                        recordButton.disabled = false; // 最初の質問が来たら録音開始可能に
                        statusDiv.textContent = 'ステータス: 面接中。最初の質問が来ました。';
                    } else {
                        outputDiv.innerHTML += `<div class="message" style="color: red;">面接開始エラー: ${data.error}</div>`;
                        statusDiv.textContent = 'ステータス: 面接開始に失敗しました。';
                        startButton.disabled = false;
                        recordButton.disabled = true;
                    }
                } catch (error) {
                    console.error('面接開始通信エラー:', error);
                    outputDiv.innerHTML += `<div class="message" style="color: red;">面接開始通信エラー: ${error.message}</div>`;
                    statusDiv.textContent = 'ステータス: 面接開始通信エラー。';
                    startButton.disabled = false;
                    recordButton.disabled = true;
                }
            };

            resetButton.onclick = async () => {
                if (!confirm('面接履歴をリセットしますか？')) {
                    return;
                }
                interviewStarted = false;
                outputDiv.innerHTML = '';
                feedbackDiv.innerHTML = '';
                statusDiv.textContent = 'ステータス: リセット完了。面接を開始してください。';
                recordButton.disabled = true;
                stopButton.disabled = true;
                startButton.disabled = false;
                if (mediaRecorder && mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                }
                if (audioPlayback) {
                    audioPlayback.pause();
                    audioPlayback.currentTime = 0;
                }
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

    app.logger.info(f"面接タイプ: {interview_type} で面接を開始します。")

    try:
        if interview_type == 'general':
            initial_prompt = "あなたは株式会社〇〇の面接官です。これから応募者に対して面接を行います。最初の質問をしてください。面接官として、常に丁寧な言葉遣いで、客観的かつ具体的に質問してください。フィードバックはまだ不要です。質問以外の情報は含めないでください。"
        else: # 'disability'
            initial_prompt = "あなたは株式会社〇〇の面接官です。障害者雇用枠の応募者に対して面接を行います。最初の質問をしてください。障害特性や合理的配慮について理解を示しつつ、丁寧な言葉遣いで、客観的かつ具体的に質問してください。フィードバックはまだ不要です。質問以外の情報は含めないでください。"

        model = genai.GenerativeModel(GEMINI_MODEL_FLASH)
        # 履歴をクリアした状態で最初の質問を生成
        response = model.generate_content(
            contents=[{"role": "user", "parts": [initial_prompt]}],
            generation_config=genai.types.GenerationConfig(temperature=0.7)
        )
        ai_response_text = response.candidates[0].content.parts[0].text
        app.logger.info(f"最初のAI質問: {ai_response_text}")

        # 履歴に追加
        interview_history.append({"role": "user", "parts": [initial_prompt]})
        interview_history.append({"role": "model", "parts": [ai_response_text]})

        # 音声合成
        tts = gTTS(text=ai_response_text, lang='ja', slow=True) # ゆっくり目の日本語音声
        audio_buffer = io.BytesIO()
        tts.save(audio_buffer)
        audio_buffer.
