import os
import io
import json
import base64
import time
from datetime import datetime

from flask import Flask, request, render_template, jsonify
from google.cloud import texttospeech_v1beta as texttospeech
from google.cloud import speech_v1p1beta1 as speech
import google.generativeai as genai
from dotenv import load_dotenv

# .env ファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__)

# Google Cloud プロジェクトID
# gcloud config get-value project で取得できるプロジェクトIDを設定
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT')

# Google Cloud API クライアントの初期化
# 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されていれば自動で認証されます
text_to_speech_client = texttospeech.TextToSpeechClient()
speech_to_text_client = speech.SpeechClient()

# Gemini APIキーを環境変数から取得
gemini_api_key = os.environ.get("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY 環境変数が設定されていません。")
genai.configure(api_key=gemini_api_key)

# Gemini Pro モデルの初期化
model = genai.GenerativeModel('gemini-pro')

# 会話履歴を格納するリスト（セッションごとに管理する必要があるため、実際にはデータベース等を使う）
conversation_history = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_interview', methods=['POST'])
def start_interview():
    global conversation_history
    conversation_history = [] # 新しい面接開始時に履歴をリセット
    interview_type = request.json.get('interview_type', 'general')

    # 面接の初期設定と最初の質問
    if interview_type == 'general':
        # 一般面接のプロンプト
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
    elif interview_type == 'technical':
        # 技術面接のプロンプト（例）
        initial_prompt = (
            "あなたは日本語の技術面接官です。以下はその面接のルールです。:\n"
            "1. 私が発言したら、それに応答してください。\n"
            "2. 日本語で応答してください。\n"
            "3. 質問は一度に一つだけにしてください。\n"
            "4. プロフェッショナルで中立的な口調を心がけてください。\n"
            "5. 面接の最後に、「面接は終了です」と明確に伝えてください。\n"
            "6. 応募者の発言内容が把握できない場合、明確化のための質問を行ってください。\n"
            "7. 技術的な概念や実装について、具体的な知識を問う質問をしてください。\n"
            "8. 長い会話を避けるために、簡潔な質問を心がけてください。\n"
            "9. 応募者の回答が抽象的だったり、理解が不足している場合は、追加の質問で深掘りしてください。\n"
            "10. 応募者が感謝の言葉を述べたら、「どういたしまして。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
            "11. 応募者が「面接を終わりにしたい」と伝えたら、「かしこまりました。本日の面接は終了です。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
            "最初の質問は「面接官：〇〇様、本日は技術面接にお越しいただきありがとうございます。まず、ご自身の得意なプログラミング言語とその経験について教えてください。」です。"
        )
    else:
        return jsonify({"error": "Invalid interview type"}), 400

    # Geminiに初期プロンプトを送信
    response = model.generate_content(initial_prompt)
    interviewer_response_text = response.text

    # 会話履歴に追加 (面接官の最初の質問)
    conversation_history.append({'role': 'user', 'parts': [initial_prompt]})
    conversation_history.append({'role': 'model', 'parts': [interviewer_response_text]})

    # 面接官の音声を生成
    audio_content = text_to_speech(interviewer_response_text)
    
    # Base64エンコードして返す
    audio_base64 = base64.b64encode(audio_content).decode('utf-8')
    return jsonify({
        'status': 'success',
        'message': interviewer_response_text,
        'audio': audio_base64
    })


@app.route('/process_audio', methods=['POST'])
def process_audio():
    audio_data_base64 = request.json.get('audio_data')
    if not audio_data_base64:
        return jsonify({"error": "No audio data provided"}), 400

    try:
        audio_data = base64.b64decode(audio_data_base64)
    except Exception as e:
        return jsonify({"error": f"Invalid Base64 audio data: {e}"}), 400

    # 音声認識
    recognized_text = speech_to_text(audio_data)

    if not recognized_text:
        # 音声が認識できなかった場合も、AIにその旨を伝えて応答を生成させる
        recognized_text = "（音声が認識できませんでした）"
        interviewer_response_text = "申し訳ありません、もう一度お話しいただけますか？"
    else:
        # Geminiにユーザーの発言と会話履歴を送信
        # generate_contentメソッドは自動的に会話履歴を管理してくれます
        # ユーザーの発言を履歴に追加
        conversation_history.append({'role': 'user', 'parts': [recognized_text]})

        try:
            # Geminiに履歴を送信して応答を取得
            response = model.generate_content(conversation_history)
            interviewer_response_text = response.text
        except Exception as e:
            # Gemini APIからのエラー処理
            print(f"Gemini API Error: {e}")
            interviewer_response_text = "現在、AIの応答に問題が発生しています。もう一度お試しください。"
            return jsonify({
                'status': 'error',
                'message': interviewer_response_text,
                'recognized_text': recognized_text,
                'audio': base64.b64encode(text_to_speech(interviewer_response_text)).decode('utf-8')
            }), 500

    # 会話履歴に追加 (Geminiの応答)
    conversation_history.append({'role': 'model', 'parts': [interviewer_response_text]})

    # 面接官の音声を生成
    audio_content = text_to_speech(interviewer_response_text)
    audio_base64 = base64.b64encode(audio_content).decode('utf-8')

    return jsonify({
        'status': 'success',
        'message': interviewer_response_text,
        'recognized_text': recognized_text,
        'audio': audio_base64
    })

# --- 音声処理関数 ---
def text_to_speech(text):
    """テキストを音声に変換する"""
    input_text = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="ja-JP",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE # 女性の声
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = text_to_speech_client.synthesize_speech(
        input=input_text, voice=voice, audio_config=audio_config
    )
    return response.audio_content

def speech_to_text(audio_data):
    """音声をテキストに変換する"""
    audio = speech.RecognitionAudio(content=audio_data)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS, # ブラウザからのフォーマットに合わせる
        sample_rate_hertz=48000, # ブラウザからのサンプリングレートに合わせる (WebM Opusの一般的なレート)
        language_code="ja-JP",
        model="latest_long", # より長時間の音声を認識できるモデル
        enable_automatic_punctuation=True # 自動句読点
    )

    try:
        response = speech_to_text_client.recognize(config=config, audio=audio)
        if response.results:
            return response.results[0].alternatives[0].transcript
        else:
            return ""
    except Exception as e:
        print(f"Speech-to-Text Error: {e}")
        return ""

if __name__ == '__main__':
    # Cloud Run のデプロイ時に使用されるポート
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
