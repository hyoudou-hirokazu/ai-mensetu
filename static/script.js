// ai-interview-app/static/script.js

const startButton = document.getElementById('startButton');
const messageDisplay = document.getElementById('message');
const aiResponseDisplay = document.getElementById('aiResponse');
let recognition; // Web Speech Recognition オブジェクト

// Web Speech APIの互換性チェック
if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    messageDisplay.textContent = "お使いのブラウザは音声認識に対応していません。Chromeなどの最新ブラウザをご利用ください。";
    startButton.disabled = true;
} else {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP'; // 日本語を設定
    recognition.continuous = false; // 連続認識をオフ
    recognition.interimResults = false; // 中間結果をオフ

    // 音声認識が開始されたとき
    recognition.onstart = () => {
        messageDisplay.textContent = "話してください...";
        startButton.disabled = true;
        startButton.textContent = "話しています...";
    };

    // 音声認識が終了したとき
    recognition.onend = () => {
        messageDisplay.textContent = "処理中...";
        startButton.textContent = "処理中...";
    };

    // 音声認識で結果が得られたとき
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        messageDisplay.textContent = `あなたの発言: ${transcript}`;
        sendToBackend(transcript);
    };

    // 音声認識でエラーが発生したとき
    recognition.onerror = (event) => {
        console.error('Speech Recognition Error:', event.error);
        messageDisplay.textContent = `音声認識エラー: ${event.error}. もう一度お試しください。`;
        startButton.disabled = false;
        startButton.textContent = "話す";
    };

    // 「話す」ボタンクリックで音声認識を開始
    startButton.addEventListener('click', () => {
        recognition.start();
    });
}

async function sendToBackend(text) {
    try {
        const response = await fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text: text })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        aiResponseDisplay.textContent = `AI面接官: ${data.response_text}`;

        // Base64エンコードされた音声データを再生
        const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
        audio.play();

        // 音声再生が終了したらボタンを再度有効にする
        audio.onended = () => {
            startButton.disabled = false;
            startButton.textContent = "話す";
            messageDisplay.textContent = "AIの返答が終わりました。次に話す場合はボタンを押してください。";
        };

    } catch (error) {
        console.error('Error sending text to backend:', error);
        messageDisplay.textContent = `AIとの通信エラー: ${error}. もう一度お試しください。`;
        startButton.disabled = false;
        startButton.textContent = "話す";
    }
}
