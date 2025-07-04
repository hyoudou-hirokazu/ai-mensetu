import os
import json
import base64
import time
from datetime import datetime

from flask import Flask, request, render_template, jsonify
from google.cloud import texttospeech
from google.cloud import speech_v1p1beta1 as speech # speech_v1p1beta1 as speech を使用
import google.generativeai as genai
from dotenv import load_dotenv

# .env ファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__)

# Google Cloud プロジェクトID
# 環境変数 GOOGLE_CLOUD_PROJECT から取得
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT')
if not PROJECT_ID:
    # 環境変数が設定されていない場合はエラーを発生させる
    raise ValueError("GOOGLE_CLOUD_PROJECT 環境変数が設定されていません。")

# Gemini APIキーを環境変数から取得
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    # 環境変数が設定されていない場合はエラーを発生させる
    raise ValueError("GEMINI_API_KEY 環境変数が設定されていません。")

# Gemini APIクライアントの設定
genai.configure(api_key=API_KEY)

# Geminiモデルの初期化
# ★ここが gemini-1.5-flash に変更されています★
model = genai.GenerativeModel('gemini-2.5-flash')
# 会話履歴を管理するためのチャットセッションを開始
chat = model.start_chat(history=[])

# Google Cloud Text-to-Speech クライアントの初期化
text_to_speech_client = texttospeech.TextToSpeechClient()

# Google Cloud Speech-to-Text クライアントの初期化
speech_to_text_client = speech.SpeechClient()

# 音声合成と音声認識のための設定
VOICE_NAME = "ja-JP-Wavenet-A" # 日本語の女性の声を選択
AUDIO_ENCODING = texttospeech.AudioEncoding.MP3 # 音声合成のエンコーディング
SAMPLE_RATE_HERTZ = 48000 # 音声認識のサンプリングレート (ブラウザからのWebM Opusの一般的なレート)

# ルートURLへのアクセス時に index.html をレンダリング
@app.route('/')
def index():
    return render_template('index.html')

# 面接開始時の処理
@app.route('/start_interview', methods=['POST'])
def start_interview():
    try:
        # リクエストボディから面接タイプを取得
        data = request.json
        interview_type = data.get('interview_type', 'general')

        # 面接タイプに応じた初期プロンプトを設定
        initial_prompt = ""
        if interview_type == 'general':
            initial_prompt = (
                "あなたは日本語の面接官です。以下はその面接のルールです。:\n"
                "1. 私が発言したら、それに応答してください。\n"
                "2. 日本語で応答してください。\n"
                "3. 質問は一度に一つだけにしてください。\n"
                "4. 自然でフレンドリーな口調を心がけてください。\n"
                "5. 面接の最後に、「面接は終了です」と明確に伝えてください。\n"
                "6. 応募者の発言内容が把握できない場合、明確化のための質問を行ってください。\n"
                "7. 質問のトーンは常にプロフェッショナルで、応募者を尊重するものである必要があります。\n"
                "8. 長い会話を避けるために、簡潔な質問を心がけてください。\n"
                "9. 応募者の回答が具体的でなかったり、深掘りが必要な場合は、具体的なエピソードや詳細を尋ねるようにしてください。\n"
                "10. 応募者が感謝の言葉を述べたら、「どういたしまして。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "11. 応募者が「面接を終わりにしたい」と伝えたら、「かしこまりました。本日の面接は終了です。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "最初の質問は「面接官：〇〇様、本日は面接にお越しいただきありがとうございます。本日は貴方のご経験について、具体的に教えていただけますでしょうか。どのような業務に携わることや、どのような成果を上げられたか？」です。"
            )
        elif interview_type == 'disability':
            initial_prompt = (
                "あなたは日本語の面接官です。以下はその面接のルールです。:\n"
                "1. 私が発言したら、それに応答してください。\n"
                "2. 日本語で応答してください。\n"
                "3. 質問は一度に一つだけにしてください。\n"
                "4. プロフェッショナルで中立的な口調を心がけてください。\n"
                "5. 面接の最後に、「面接は終了です」と明確に伝えてください。\n"
                "6. 応募者の発言内容が把握できない場合、明確化のための質問を行ってください。\n"
                "7. 技術的な概念や実装について、具体的な知識を問う質問をしてください。\n" # 技術面接のプロンプトだが、障害者雇用向けに調整が必要
                "8. 長い会話を避けるために、簡潔な質問を心がけてください。\n"
                "9. 応募者の回答が抽象的だったり、理解が不足している場合は、追加の質問で深掘りしてください。\n"
                "10. 応募者が感謝の言葉を述べたら、「どういたしまして。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "11. 応募者が「面接を終わりにしたい」と伝えたら、「かしこまりました。本日の面接は終了です。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "最初の質問は「面接官：〇〇様、本日は障害者雇用の面接にお越しいただきありがとうございます。まず、ご自身の障害特性と、業務遂行上必要となる合理的配慮について教えていただけますでしょうか？」です。" # 障害者雇用向けに調整
            )
        else:
            return jsonify({"error": "Invalid interview type"}), 400

        # Geminiモデルに初期プロンプトを送信し、応答を生成させる
        response = chat.send_message(initial_prompt)
        ai_text = response.text

        # Text-to-SpeechでAIの応答を音声に変換
        synthesis_input = texttospeech.SynthesisInput(text=ai_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="ja-JP",
            name=VOICE_NAME
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=AUDIO_ENCODING
        )
        tts_response = text_to_speech_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')

        return jsonify({
            'status': 'success',
            'message': ai_text,
            'audio': audio_content_base64
        })

    except Exception as e:
        # エラーが発生した場合の処理
        print(f"Error in start_interview: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': '面接の開始中にエラーが発生しました。'})

# 音声処理エンドポイント
@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        # リクエストボディからBase64エンコードされた音声データを取得
        data = request.json
        audio_data_base64 = data.get('audio_data')

        if not audio_data_base64:
            return jsonify({'status': 'error', 'error': 'No audio data received.'})

        # Base64データをデコードしてバイナリ音声データに戻す
        audio_content = base64.b64decode(audio_data_base64)

        # Speech-to-Textで音声をテキストに変換
        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS, # ChromeのMediaRecorderのデフォルトエンコーディング
            sample_rate_hertz=SAMPLE_RATE_HERTZ,
            language_code="ja-JP",
        )
        stt_response = speech_to_text_client.recognize(config=config, audio=audio)

        recognized_text = ""
        if stt_response.results:
            # 認識されたテキストを取得
            recognized_text = stt_response.results[0].alternatives[0].transcript

        if not recognized_text:
            # 音声が認識できなかった場合の応答
            return jsonify({
                'status': 'success',
                'recognized_text': "",
                'message': 'すみません、あなたの音声を認識できませんでした。もう一度お願いします。',
                'audio': "" # 音声認識失敗時はAIの音声を返さない
            })

        # Geminiモデルにユーザーの応答を送信し、次の質問を生成させる
        chat_response = chat.send_message(recognized_text)
        ai_text = chat_response.text

        # Text-to-SpeechでAIの応答を音声に変換
        synthesis_input = texttospeech.SynthesisInput(text=ai_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="ja-JP",
            name=VOICE_NAME
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=AUDIO_ENCODING
        )
        tts_response = text_to_speech_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')

        # ここでGeminiからのフィードバックを処理するロジックを追加することも可能
        # 例: feedback_text = chat_response.parts[...].feedback_info など

        return jsonify({
            'status': 'success',
            'recognized_text': recognized_text,
            'message': ai_text,
            'audio': audio_content_base64
            # 'feedback': feedback_text # 必要に応じてフィードバックも返す
        })

    except Exception as e:
        # エラーが発生した場合の処理
        print(f"Error in process_audio: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': '音声の処理中にエラーが発生しました。', 'recognized_text': ''})

# アプリケーションのエントリーポイント
if __name__ == '__main__':
    # Cloud Run環境ではPORT環境変数が設定されるため、それを使用
    port = int(os.environ.get('PORT', 8080))
    # Flaskアプリケーションを実行 (Cloud RunではデバッグモードはFalse推奨)
    app.run(host='0.0.0.0', port=port, debug=False)
