import os
import json
import base64
import time
from datetime import datetime
import re # 正規表現モジュールをインポート

from flask import Flask, request, render_template, jsonify, url_for
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
AUDIO_ENCODING = texttospeech.AudioEncoding.MP3
SAMPLE_RATE_HERTZ = 48000

# 面接者の名前を保持するグローバル変数（名前入力がなくなったため、ダミーまたは「あなた」のような表現に）
applicant_name_global = "あなた"

@app.route('/')
def index():
    return render_template('index.html')

# 画像パスを提供する新しいエンドポイント - ファイル名を英数字に修正
@app.route('/get_image_paths', methods=['GET'])
def get_image_paths():
    try:
        male_image_path = url_for('static', filename='images/male_interviewer.jpg')
        female_image_path = url_for('static', filename='images/female_interviewer.jpg')
        return jsonify({
            'status': 'success',
            'male_image_path': male_image_path,
            'female_image_path': female_image_path
        })
    except Exception as e:
        print(f"Error in get_image_paths: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/start_interview', methods=['POST'])
def start_interview():
    global applicant_name_global
    try:
        data = request.json
        interview_type = data.get('interview_type', 'general')
        voice_gender = data.get('voice_gender', 'FEMALE')

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
                f"最初の質問は「本日は面接にお越しいただきありがとうございます。これから面接をはじめさせていただきます。まず、自己紹介もふまえて、これまでのご経験、ご経歴を一通り教えていただけますか？」です。"
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
                f"最初の質問は「本日は面接にお越しいただきありがとうございます。これから面接をはじめさせていただきます。まず、自己紹介もふまえて、これまでのご経験、ご経歴を一通り教えていただけますか？」です。"
            )
        else:
            return jsonify({"error": "Invalid interview type"}), 400

        response = chat.send_message(initial_prompt)
        ai_text = response.text

        tts_response = synthesize_speech(ai_text, voice_gender)
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
        end_interview_prompt = data.get('end_interview_prompt')
        voice_gender = data.get('voice_gender', 'FEMALE')

        recognized_text = ""
        if audio_data_base64:
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

        if not recognized_text and not end_interview_prompt:
            ai_text = 'すみません、あなたの音声を認識できませんでした。もう一度お願いします。'
            tts_response = synthesize_speech(ai_text, voice_gender)
            audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')
            return jsonify({
                'status': 'success',
                'recognized_text': "",
                'message': ai_text,
                'audio': audio_content_base64,
                'feedback': '音声が認識されませんでした。'
            })
        
        if end_interview_prompt:
            response = chat.send_message(end_interview_prompt)
            ai_text = response.text
        else:
            chat_response_prompt = f"応募者の回答: {recognized_text}\n\n面接官として、この回答に基づいて次の質問を簡潔に、かつ箇条書きや特殊文字（例: *）を使用せずにしてください。"
            response = chat.send_message(chat_response_prompt)
            ai_text = response.text

        tts_response = synthesize_speech(ai_text, voice_gender)
        audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')

        return jsonify({
            'status': 'success',
            'recognized_text': recognized_text,
            'message': ai_text,
            'audio': audio_content_base64,
            'feedback': ''
        })

    except Exception as e:
        print(f"Error in process_audio: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': '音声の処理中にエラーが発生しました。', 'recognized_text': '', 'feedback': 'フィードバックの取得中にエラーが発生しました。'})

@app.route('/get_feedback', methods=['POST'])
def get_feedback():
    global applicant_name_global
    try:
        data = request.json
        conversation_history_text = data.get('conversation_history', '')

        feedback_prompt = (
            f"あなたは面接練習アプリの面接官です。以下の面接履歴全体を評価し、面接における「あなた」の良かった点、改善点、総合評価を簡潔に、箇条書きや特殊文字（例: *）を使用せずにフィードバックしてください。\n"
            "改善点については、具体的な返答例を一つ含めてください。返答例は「返答例: [具体的な返答例]」の形式で記述してください。\n"
            "各カテゴリ（良かった点、改善点、総合評価）は必ず新しい行から始めてください。\n"
            "最後に、100点満点での評価点数を「評価点数: [点数]/100」の形式で出力してください。点数は整数でお願いします。\n\n"
            "面接履歴:\n"
            f"{conversation_history_text}\n\n"
            "フィードバック:"
        )
        
        feedback_model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')
        feedback_response = feedback_model.generate_content(feedback_prompt)
        feedback_text = feedback_response.text

        # 評価点数を抽出
        score_match = re.search(r'評価点数:\s*(\d+)/100', feedback_text)
        score = int(score_match.group(1)) if score_match else None

        return jsonify({
            'status': 'success',
            'feedback': feedback_text,
            'score': score
        })
    except Exception as e:
        print(f"Error in get_feedback: {e}")
        return jsonify({'status': 'error', 'error': str(e), 'message': 'フィードバックの生成中にエラーが発生しました。'})


def synthesize_speech(text, gender):
    """テキストを音声に変換するヘルパー関数"""
    input_text = texttospeech.SynthesisInput(text=text)
    
    # 性別に基づいて音声を選択
    if gender == "MALE":
        voice_name = "ja-JP-Wavenet-D"
        ssml_gender = texttospeech.SsmlVoiceGender.MALE
    else: # デフォルトは女性
        voice_name = "ja-JP-Wavenet-A"
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
