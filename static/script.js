// static/script.js

document.addEventListener('DOMContentLoaded', () => {
    const interviewTypeSelect = document.getElementById('interview-type');
    const startInterviewBtn = document.getElementById('start-interview-btn');
    const recordBtn = document.getElementById('record-btn');
    const stopRecordBtn = document.getElementById('stop-record-btn');
    const aiMessageElem = document.getElementById('ai-message');
    const aiAudioElem = document.getElementById('ai-audio');
    const userTranscriptElem = document.getElementById('user-transcript');
    const statusMessageElem = document.getElementById('status-message');
    const feedbackLogElem = document.getElementById('feedback-log');
    const currentFeedbackElem = document.getElementById('current-feedback');
    const historyLogElem = document.getElementById('history-log');

    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;

    // UI初期状態設定
    function resetUI() {
        startInterviewBtn.disabled = false;
        recordBtn.disabled = true;
        stopRecordBtn.disabled = true;
        aiMessageElem.textContent = '面接を開始します。準備ができたら「面接を開始」ボタンを押してください。';
        aiAudioElem.style.display = 'none';
        aiAudioElem.src = '';
        userTranscriptElem.textContent = '';
        statusMessageElem.textContent = '準備完了';
        currentFeedbackElem.textContent = '面接中はフィードバックが表示されます。';
        historyLogElem.innerHTML = ''; // 履歴をクリア
        // feedbackLogElem.innerHTML = '<p id="current-feedback">面接中はフィードバックが表示されます。</p>'; // この行は currentFeedbackElem で管理するため不要
    }

    resetUI(); // ページ読み込み時にUIを初期化

    // 面接開始ボタンのクリックイベント
    startInterviewBtn.addEventListener('click', async () => {
        resetUI(); // 新しい面接開始時にUIをリセット
        const interviewType = interviewTypeSelect.value;
        statusMessageElem.textContent = '面接を開始中...';
        startInterviewBtn.disabled = true; // 面接開始中は無効化

        try {
            const response = await fetch('/start_interview', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ interview_type: interviewType })
            });

            const data = await response.json();

            if (data.status === 'success') {
                aiMessageElem.textContent = data.message;
                aiAudioElem.src = 'data:audio/mp3;base64,' + data.audio;
                aiAudioElem.style.display = 'block'; // AI音声プレーヤーを表示
                aiAudioElem.play();
                statusMessageElem.textContent = 'AIが質問しています。';

                // 会話履歴に追加
                addHistory('AI', data.message);

                // AIの音声再生が終了したら録音ボタンを有効にする
                aiAudioElem.onended = () => {
                    recordBtn.disabled = false;
                    statusMessageElem.textContent = '録音可能です。';
                };

            } else {
                aiMessageElem.textContent = '面接開始エラー: ' + (data.error || '不明なエラー');
                statusMessageElem.textContent = 'エラーが発生しました。';
                startInterviewBtn.disabled = false; // 再度開始できるように
            }
        } catch (error) {
            console.error('面接開始エラー:', error);
            aiMessageElem.textContent = 'サーバーとの通信に失敗しました。';
            statusMessageElem.textContent = 'エラーが発生しました。';
            startInterviewBtn.disabled = false; // 再度開始できるように
        }
    });

    // 録音開始ボタンのクリックイベント
    recordBtn.addEventListener('click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = event => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm; codecs=opus' });
                const reader = new FileReader();
                reader.readAsDataURL(audioBlob);
                reader.onloadend = async () => {
                    const base64data = reader.result.split(',')[1];
                    await sendAudioToServer(base64data);
                };
            };

            mediaRecorder.start();
            isRecording = true;
            recordBtn.disabled = true;
            stopRecordBtn.disabled = false;
            statusMessageElem.textContent = '録音中...';
            userTranscriptElem.textContent = '（録音中...）';
            aiMessageElem.textContent = 'AI: （あなたの回答を待っています）'; // AIメッセージを一時的にクリア
            aiAudioElem.style.display = 'none'; // AI音声プレーヤーを非表示
            currentFeedbackElem.textContent = 'フィードバックを生成中...'; // ★追加★
        } catch (error) {
            console.error('マイクアクセスエラー:', error);
            statusMessageElem.textContent = 'マイクへのアクセスが拒否されました。';
            recordBtn.disabled = false;
            stopRecordBtn.disabled = true;
        }
    });

    // 録音停止ボタンのクリックイベント
    stopRecordBtn.addEventListener('click', () => {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            recordBtn.disabled = true;
            stopRecordBtn.disabled = true;
            statusMessageElem.textContent = '音声を処理中...';
        }
    });

    // 音声データをサーバーに送信する関数
    async function sendAudioToServer(base64data) {
        try {
            const response = await fetch('/process_audio', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ audio_data: base64data })
            });

            const data = await response.json();

            if (data.status === 'success') {
                userTranscriptElem.textContent = data.recognized_text;
                aiMessageElem.textContent = data.message;
                aiAudioElem.src = 'data:audio/mp3;base64,' + data.audio;
                aiAudioElem.style.display = 'block';
                aiAudioElem.play();
                statusMessageElem.textContent = 'AIが応答しました。';

                // 会話履歴に追加 (ユーザーの発言とAIの応答)
                addHistory('あなた', data.recognized_text);
                addHistory('AI', data.message);

                // ★フィードバックを表示するロジックを追加★
                currentFeedbackElem.textContent = data.feedback || 'フィードバックはありません。';

                // AIの音声再生が終了したら録音ボタンを再度有効にする
                aiAudioElem.onended = () => {
                    recordBtn.disabled = false;
                    statusMessageElem.textContent = '録音可能です。';
                };

            } else {
                userTranscriptElem.textContent = data.recognized_text || '認識できませんでした。';
                aiMessageElem.textContent = 'AI応答エラー: ' + (data.message || '不明なエラー');
                statusMessageElem.textContent = 'エラーが発生しました。';
                recordBtn.disabled = false;
                // ★エラー時もフィードバックを表示★
                currentFeedbackElem.textContent = data.feedback || 'フィードバックの取得中にエラーが発生しました。';
            }
        } catch (error) {
            console.error('音声処理エラー:', error);
            statusMessageElem.textContent = '音声処理中にエラーが発生しました。';
            recordBtn.disabled = false;
            currentFeedbackElem.textContent = 'フィードバックの取得中にエラーが発生しました。'; // ★追加★
        }
    }

    // 会話履歴に追加するヘルパー関数
    function addHistory(role, text) {
        const entryDiv = document.createElement('div');
        entryDiv.classList.add('entry', role.toLowerCase());
        entryDiv.innerHTML = `<span class="role">${role}:</span> ${text}`;
        historyLogElem.appendChild(entryDiv);
        historyLogElem.scrollTop = historyLogElem.scrollHeight;
    }

    historyLogElem.innerHTML = '';
});
