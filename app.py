import os
import json
import base64
import time
from datetime import datetime
import re # 正規表現モジュールをインポート
import logging # ロギングモジュールをインポート

# ロギングを設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from flask import Flask, request, render_template, jsonify, url_for
    from google.cloud import texttospeech
    from google.cloud import speech_v1p1beta1 as speech
    import google.generativeai as genai
    from dotenv import load_dotenv
    logger.info("All necessary modules imported successfully.")
except ImportError as e:
    logger.error(f"Failed to import a module: {e}")
    # モジュールのインポートに失敗した場合、アプリケーションを終了
    exit(1)

# .env ファイルから環境変数を読み込む
try:
    load_dotenv()
    logger.info(".env file loaded.")
except Exception as e:
    logger.warning(f"Could not load .env file: {e}. Assuming environment variables are set directly.")

app = Flask(__name__)

# Google Cloud プロジェクトID
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT')
if not PROJECT_ID:
    logger.error("GOOGLE_CLOUD_PROJECT environment variable is not set.")
    raise ValueError("GOOGLE_CLOUD_PROJECT 環境変数が設定されていません。")
else:
    logger.info(f"GOOGLE_CLOUD_PROJECT is set to: {PROJECT_ID}")

# Gemini APIキーを環境変数から取得
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    logger.error("GEMINI_API_KEY environment variable is not set.")
    raise ValueError("GEMINI_API_KEY 環境変数が設定されていません。")
else:
    logger.info("GEMINI_API_KEY is set (value hidden for security).")

# Gemini APIクライアントの設定
try:
    genai.configure(api_key=API_KEY)
    logger.info("Gemini API client configured.")
except Exception as e:
    logger.error(f"Failed to configure Gemini API client: {e}")
    exit(1)

# Geminiモデルの初期化
try:
    model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')
    chat = model.start_chat(history=[])
    logger.info("Gemini model and chat initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Gemini model or chat: {e}")
    exit(1)

# Google Cloud Text-to-Speech クライアントの初期化
try:
    text_to_speech_client = texttospeech.TextToSpeechClient()
    logger.info("Google Cloud Text-to-Speech client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Text-to-Speech client: {e}")
    exit(1)

# Google Cloud Speech-to-Text クライアントの初期化
try:
    speech_to_text_client = speech.SpeechClient()
    logger.info("Google Cloud Speech-to-Text client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Speech-to-Text client: {e}")
    exit(1)

# 音声合成と音声認識のための設定
AUDIO_ENCODING = texttospeech.AudioEncoding.MP3
SAMPLE_RATE_HERTZ = 48000
logger.info("Audio encoding and sample rate configured.")

# 面接者の名前を保持するグローバル変数（名前入力がなくなったため、ダミーまたは「あなた」のような表現に）
applicant_name_global = "あなた"
logger.info("Applicant name global variable set.")

@app.route('/')
def index():
    logger.info("Serving index.html.")
    return render_template('index.html')

@app.route('/get_image_paths', methods=['GET'])
def get_image_paths():
    try:
        male_image_path = url_for('static', filename='images/male_interviewer.jpg')
        female_image_path = url_for('static', filename='images/female_interviewer.jpg')
        logger.info(f"Image paths generated: male={male_image_path}, female={female_image_path}")
        return jsonify({
            'status': 'success',
            'male_image_path': male_image_path,
            'female_image_path': female_image_path
        })
    except Exception as e:
        logger.error(f"Error in get_image_paths: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/start_interview', methods=['POST'])
def start_interview():
    global applicant_name_global
    try:
        data = request.json
        interview_type = data.get('interview_type', 'general')
        voice_gender = data.get('voice_gender', 'FEMALE')
        logger.info(f"Starting interview with type: {interview_type}, gender: {voice_gender}")

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
            logger.error(f"Invalid interview type: {interview_type}")
            return jsonify({"error": "Invalid interview type"}), 400

        response = chat.send_message(initial_prompt)
        ai_text = response.text
        logger.info(f"AI initial message generated: {ai_text[:50]}...") # 最初の50文字をログ

        tts_response = synthesize_speech(ai_text, voice_gender)
        audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')
        logger.info("AI audio synthesized.")

        return jsonify({
            'status': 'success',
            'message': ai_text,
            'audio': audio_content_base64
        })

    except Exception as e:
        logger.error(f"Error in start_interview: {e}", exc_info=True) # スタックトレースも出力
        return jsonify({'status': 'error', 'error': str(e), 'message': '面接の開始中にエラーが発生しました。'})

@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        data = request.json
        audio_data_base64 = data.get('audio_data')
        end_interview_prompt = data.get('end_interview_prompt')
        voice_gender = data.get('voice_gender', 'FEMALE')
        logger.info(f"Processing audio. End interview prompt: {end_interview_prompt is not None}")

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
                logger.info(f"Speech recognized: {recognized_text}")
            else:
                logger.info("No speech recognized.")

        if not recognized_text and not end_interview_prompt:
            ai_text = 'すみません、あなたの音声を認識できませんでした。もう一度お願いします。'
            tts_response = synthesize_speech(ai_text, voice_gender)
            audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')
            logger.warning("No recognized text and no end interview prompt. Asking for re-attempt.")
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
            logger.info(f"AI responded to end interview prompt: {ai_text[:50]}...")
        else:
            chat_response_prompt = f"応募者の回答: {recognized_text}\n\n面接官として、この回答に基づいて次の質問を簡潔に、かつ箇条書きや特殊文字（例: *）を使用せずにしてください。"
            response = chat.send_message(chat_response_prompt)
            ai_text = response.text
            logger.info(f"AI responded to user input: {ai_text[:50]}...")

        tts_response = synthesize_speech(ai_text, voice_gender)
        audio_content_base64 = base64.b64encode(tts_response.audio_content).decode('utf-8')
        logger.info("AI audio synthesized for response.")

        return jsonify({
            'status': 'success',
            'recognized_text': recognized_text,
            'message': ai_text,
            'audio': audio_content_base64,
            'feedback': ''
        })

    except Exception as e:
        logger.error(f"Error in process_audio: {e}", exc_info=True)
        return jsonify({'status': 'error', 'error': str(e), 'message': '音声の処理中にエラーが発生しました。', 'recognized_text': '', 'feedback': 'フィードバックの取得中にエラーが発生しました。'})

@app.route('/get_feedback', methods=['POST'])
def get_feedback():
    global applicant_name_global
    try:
        data = request.json
        conversation_history_text = data.get('conversation_history', '')
        logger.info("Generating feedback.")

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
        logger.info(f"Feedback generated: {feedback_text[:50]}...")

        # 評価点数を抽出
        score_match = re.search(r'評価点数:\s*(\d+)/100', feedback_text)
        score = int(score_match.group(1)) if score_match else None
        logger.info(f"Extracted score: {score}")

        return jsonify({
            'status': 'success',
            'feedback': feedback_text,
            'score': score
        })
    except Exception as e:
        logger.error(f"Error in get_feedback: {e}", exc_info=True)
        return jsonify({'status': 'error', 'error': str(e), 'message': 'フィードバックの生成中にエラーが発生しました。'})


def synthesize_speech(text, gender):
    """テキストを音声に変換するヘルパー関数"""
    try:
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
        logger.info(f"Synthesizing speech for text: {text[:30]}... with voice: {voice_name}")
        return text_to_speech_client.synthesize_speech(
            input=input_text, voice=voice, audio_config=audio_config
        )
    except Exception as e:
        logger.error(f"Error in synthesize_speech: {e}", exc_info=True)
        raise # エラーを再スローして呼び出し元で処理させる

if __name__ == '__main__':
    logger.info("Starting Flask application.")
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
