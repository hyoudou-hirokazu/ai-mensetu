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
chat = model.start_chat(history=[]) # グローバルなチャットセッション

# Google Cloud Text-to-Speech クライアントの初期化
text_to_speech_client = texttospeech.TextToSpeechClient()

# Google Cloud Speech-to-Text クライアントの初期化
speech_to_text_client = speech.SpeechClient()

# 音声合成と音声認識のための設定
# VOICE_NAME は動的に設定されるため、デフォルトは空に
AUDIO_ENCODING = texttospeech.AudioEncoding.MP3
SAMPLE_RATE_HERTZ = 48000

# 面接者の名前を保持するグローバル変数（簡易的なもの。本来はセッション管理が必要）
applicant_name_global = "応募者"
voice_gender_global = "FEMALE" # デフォルトは女性

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_interview', methods=['POST'])
def start_interview():
    global applicant_name_global, voice_gender_global
    try:
        data = request.json
        interview_type = data.get('interview_type', 'general')
        applicant_name = data.get('applicant_name', '〇〇') # 名前を取得
        voice_gender = data.get('voice_gender', 'FEMALE') # 音声タイプを取得

        applicant_name_global = applicant_name # グローバル変数に保存
        voice_gender_global = voice_gender # グローバル変数に保存

        # 新しい面接開始時にチャット履歴をリセット
        chat.history.clear()

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
                "8. 長い会話を避けるために、簡潔な質問を心がけてください。箇条書きや特殊文字（例: *）を使用しないでください。\n"
                "9. 応募者の回答が具体的でなかったり、深掘りが必要な場合は、具体的なエピソードや詳細を尋ねるようにしてください。\n"
                "10. 応募者が感謝の言葉を述べたら、「どういたしまして。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "11. 応募者が「面接を終わりにしたい」と伝えたら、「かしこまりました。本日の面接は終了です。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                f"最初の質問は「{applicant_name}様、本日は面接にお越しいただきありがとうございます。本日は貴方のご経験について、具体的に教えていただけますでしょうか。どのような業務に携わることや、どのような成果を上げられたか？」です。" # ★名前を反映★
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
                "8. 長い会話を避けるために、簡潔な質問を心がけてください。箇条書きや特殊文字（例: *）を使用しないでください。\n"
                "9. 応募者の回答が抽象的だったり、理解が不足している場合は、追加の質問で深掘りしてください。\n"
                "10. 応募者が感謝の言葉を述べたら、「どういたしまして。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                "11. 応募者が「面接を終わりにしたい」と伝えたら、「かしこまりました。本日の面接は終了です。面接にご参加いただきありがとうございました。結果については後日連絡いたします。」と伝えて面接を終了してください。\n"
                f"最初の質問は「{applicant_name}様、本日は障害者雇用の面接にお越しいただきありがとうございます。まず、ご自身の障害特性と、業務遂行上必要となる合理的配慮について教えていただけますでしょうか？」です。" # ★名前を反映★
            )
        else:
            return jsonify({"error": "Invalid interview type"}), 400

        # Geminiモデルに初期プロンプトを送信し、応答を生成させる
        response = chat.send_message(initial_prompt)
        ai_text = response.text

        # Text-to-SpeechでAIの応答を音声に変換
        tts_response = synthesize_speech(ai_text, voice_gender_global) # ★音声タイプを渡す★
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
    global applicant_name_global, voice_gender_global
    try:
        data = request.json
        audio_data_base64 = data.get('audio_data')
        end_interview_prompt = data.get('end_interview_prompt') # 面接終了を促すプロンプト

        recognized_text = ""
        if audio_data_base64: # 音声データがある場合のみ音声認識
            audio_content = base64.b64decode(audio_data_base64)
            audio = speech.RecognitionAudio(content=audio_content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                sample_rate_hertz=SAMPLE_RATE_HERTZ,
                language_code="ja-JP",
            )
            stt_response = speech_to_text_client.recognize(config=config, audio=audio)

            if stt_response.results:
                recognized_text = stt_response.results[0].alternatives[0].transcript

        # 音声認識ができなかった場合、または面接終了プロンプトが送られた場合
        if not recognized_text and not end_interview_prompt:
            ai_text = 'すみません、あなたの音声を認識できませんでした。もう一度お願いします。'
            tts_response = synthesize_speech(ai_text, voice_gender_global)
            audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')
            return jsonify({
                'status': 'success',
                'recognized_text': "",
                'message': ai_text,
                'audio': audio_content_base64,
                'feedback': '音声が認識されませんでした。'
            })
        
        # 面接終了を促すプロンプトが送られた場合
        if end_interview_prompt:
            response = chat.send_message(end_interview_prompt)
            ai_text = response.text
        else:
            # Geminiモデルにユーザーの応答を送信し、次の質問を生成させる
            chat_response_prompt = f"応募者の回答: {recognized_text}\n\n面接官として、この回答に基づいて次の質問を簡潔に、かつ箇条書きや特殊文字（例: *）を使用せずにしてください。"
            response = chat.send_message(chat_response_prompt)
            ai_text = response.text

        tts_response = synthesize_speech(ai_text, voice_gender_global) # ★音声タイプを渡す★
        audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')

        # 面接中のフィードバックは返さない
        return jsonify({
            'status': 'success',
            'recognized_text': recognized_text,
            'message': ai_text,
            'audio': audio_content_base64,
            'feedback': '' # ★面接中はフィードバックを空にする★
        })

    except Exception as e:
        print(f"Error in process_audio: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': '音声の処理中にエラーが発生しました。', 'recognized_text': '', 'feedback': 'フィードバックの取得中にエラーが発生しました。'})

# 総括フィードバック取得エンドポイント
@app.route('/get_final_feedback', methods=['POST'])
def get_final_feedback():
    global applicant_name_global
    try:
        data = request.json
        conversation_history_text = data.get('conversation_history', '')

        feedback_prompt = (
            f"面接練習アプリの面接官として、以下の面接履歴全体を評価し、{applicant_name_global}様の面接の改善点と良かった点を簡潔に、箇条書きや特殊文字（例: *）を使用せずに総括してフィードバックしてください。\n\n"
            "面接履歴:\n"
            f"{conversation_history_text}\n\n"
            "フィードバック:"
        )
        
        # 新しいチャットセッションでフィードバックを生成（会話履歴とは独立）
        feedback_model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')
        feedback_response = feedback_model.generate_content(feedback_prompt)
        final_feedback_text = feedback_response.text

        return jsonify({
            'status': 'success',
            'feedback': final_feedback_text
        })
    except Exception as e:
        print(f"Error in get_final_feedback: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': '最終フィードバックの生成中にエラーが発生しました。'})

# 音声合成ヘルパー関数
def synthesize_speech(text, gender):
    """テキストを音声に変換するヘルパー関数"""
    input_text = texttospeech.SynthesisInput(text=text)
    
    # 性別に基づいて音声を選択
    if gender == "MALE":
        voice_name = "ja-JP-Wavenet-B" # 男性声の例
        ssml_gender = texttospeech.SsmlVoiceGender.MALE
    else: # デフォルトは女性
        voice_name = "ja-JP-Wavenet-A" # 女性声の例
        ssml_gender = texttospeech.SsmlVoiceGender.FEMALE

    voice = texttospeech.VoiceSelectionParams(
        language_code="ja-JP",
        name=voice_name,
        ssml_gender=ssml_gender
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=AUDIO_ENCODING
    )
    return text_to_speech_client.synthesize_speech(
        input=input_text, voice=voice, audio_config=audio_config
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
