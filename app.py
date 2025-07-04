import os
import json
import base64
import time
from datetime import datetime

from flask import Flask, request, render_template, jsonify
from google.cloud import texttospeech
from google.cloud import speech_v1p1beta1 as speech
import google.generativeai as genai
from dotenv import load_dotenv

# .env ファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__)

# Google Cloud プロジェクトID
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT')
if not PROJECT_ID:
    raise ValueError("GOOGLE_CLOUD_PROJECT 環境変数が設定されていません。")

# Gemini APIキーを環境変数から取得
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY 環境変数が設定されていません。")

# Gemini APIクライアントの設定
genai.configure(api_key=API_KEY)

# Geminiモデルの初期化
model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')
chat = model.start_chat(history=[])

# Google Cloud Text-to-Speech クライアントの初期化
text_to_speech_client = texttospeech.TextToSpeechClient()

# Google Cloud Speech-to-Text クライアントの初期化
speech_to_text_client = speech.SpeechClient()

# 音声合成と音声認識のための設定
VOICE_NAME = "ja-JP-Wavenet-A"
AUDIO_ENCODING = texttospeech.AudioEncoding.MP3
SAMPLE_RATE_HERTZ = 48000

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_interview', methods=['POST'])
def start_interview():
    try:
        data = request.json
        interview_type = data.get('interview_type', 'general')

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
                "8. 長い会話を避けるために、簡潔な質問を心がけてください。箇条書きや特殊文字（例: *）を使用しないでください。\n" # ★追加★
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
                "7. 技術的な概念や実装について、具体的な知識を問う質問をしてください。\n"
                "8. 長い会話を避けるために、簡潔な質問を心がけてください。箇条書きや特殊文字（例: *）を使用しないでください。\n" # ★追加★
                "9. 応募者の回答が抽象的だったり、理解が不足している場合は、追加の質問で深掘りしてください。\n"
                "10. 応募者が感謝の言葉を述べたら、「どういたしまして。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "11. 応募者が「面接を終わりにしたい」と伝えたら、「かしこまりました。本日の面接は終了です。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "最初の質問は「面接官：〇〇様、本日は障害者雇用の面接にお越しいただきありがとうございます。まず、ご自身の障害特性と、業務遂行上必要となる合理的配慮について教えていただけますでしょうか？」です。"
            )
        else:
            return jsonify({"error": "Invalid interview type"}), 400

        response = chat.send_message(initial_prompt)
        ai_text = response.text

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
        print(f"Error in start_interview: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': '面接の開始中にエラーが発生しました。'})

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        data = request.json
        audio_data_base64 = data.get('audio_data')

        if not audio_data_base64:
            return jsonify({'status': 'error', 'error': 'No audio data received.'})

        audio_content = base64.b64decode(audio_data_base64)

        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            sample_rate_hertz=SAMPLE_RATE_HERTZ,
            language_code="ja-JP",
        )
        stt_response = speech_to_text_client.recognize(config=config, audio=audio)

        recognized_text = ""
        if stt_response.results:
            recognized_text = stt_response.results[0].alternatives[0].transcript

        if not recognized_text:
            return jsonify({
                'status': 'success',
                'recognized_text': "",
                'message': 'すみません、あなたの音声を認識できませんでした。もう一度お願いします。',
                'audio': "",
                'feedback': '音声が認識されませんでした。'
            })

        # Geminiモデルにユーザーの応答を送信し、次の質問を生成させる
        # ここでAIの応答を簡潔にするための指示を追加
        chat_response_prompt = f"応募者の回答: {recognized_text}\n\n面接官として、この回答に基づいて次の質問を簡潔に、かつ箇条書きや特殊文字（例: *）を使用せずにしてください。" # ★変更★
        chat_response = chat.send_message(chat_response_prompt) # ★変更★
        ai_text = chat_response.text

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

        # ★フィードバックを生成するロジックを強化★
        feedback_prompt = f"以下の応募者の回答について、面接官として改善点や良い点を簡潔に、箇条書きや特殊文字（例: *）を使用せずにフィードバックしてください。\n回答: {recognized_text}"
        feedback_response = model.generate_content(feedback_prompt)
        feedback_text = feedback_response.text


        return jsonify({
            'status': 'success',
            'recognized_text': recognized_text,
            'message': ai_text,
            'audio': audio_content_base64,
            'feedback': feedback_text
        })

    except Exception as e:
        print(f"Error in process_audio: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': '音声の処理中にエラーが発生しました。', 'recognized_text': '', 'feedback': 'フィードバックの取得中にエラーが発生しました。'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
