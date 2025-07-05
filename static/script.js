// static/script.js

document.addEventListener('DOMContentLoaded', () => {
    const interviewTypeSelect = document.getElementById('interview-type');
    const voiceGenderSelect = document.getElementById('voice-gender');
    const startInterviewBtn = document.getElementById('start-interview-btn');
    const recordBtn = document.getElementById('record-btn');
    const stopRecordBtn = document.getElementById('stop-record-btn');
    const feedbackButton = document.getElementById('feedback-button');
    const aiMessageElem = document.getElementById('ai-message');
    const aiAudioElem = document.getElementById('ai-audio');
    const userTranscriptElem = document.getElementById('user-transcript');
    const statusMessageElem = document.getElementById('status-message');
    const feedbackContentElem = document.getElementById('feedback-content');
    const historyLogElem = document.getElementById('history-log');

    // UI初期状態設定
    function resetUI() {
        startInterviewBtn.disabled = false;
        recordBtn.disabled = true;
        stopRecordBtn.disabled = true;
        feedbackButton.disabled = true;
        aiMessageElem.textContent = '面接を開始します。準備ができたら「面接を開始」ボタンを押してください。';
        aiAudioElem.style.display = 'none';
        aiAudioElem.src = '';
        userTranscriptElem.textContent = '';
        statusMessageElem.textContent = '準備完了';
        feedbackContentElem.innerHTML = 'フィードバックボタンを押すか、面接終了後にここにフィードバックが表示されます。';
        historyLogElem.innerHTML = ''; // 履歴をクリア
    }

    resetUI(); // UIをリセット

    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;

    // 面接開始ボタンのクリックイベント
    startInterviewBtn.addEventListener('click', async () => {
        console.log('「面接を開始」ボタンがクリックされました。');
        resetUI(); // 新しい面接開始時にUIをリセット
        const interviewType = interviewTypeSelect.value;
        const voiceGender = voiceGenderSelect.value; // 面接官の音声性別を取得
        
        statusMessageElem.textContent = '面接を開始中...';
        startInterviewBtn.disabled = true; // 面接開始中は無効化

        try {
            console.log('サーバーへ /start_interview リクエストを送信中...');
            const response = await fetch('/start_interview', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    interview_type: interviewType,
                    voice_gender: voiceGender // 音声性別をサーバーに送信
                })
            });

            const data = await response.json();
            console.log('サーバーからの応答:', data);

            if (data.status === 'success') {
                aiMessageElem.textContent = data.message;
                aiAudioElem.src = 'data:audio/mp3;base64,' + data.audio;
                aiAudioElem.style.display = 'block';
                aiAudioElem.play();
                statusMessageElem.textContent = 'AIが質問しています。';

                addHistory('AI', data.message);

                aiAudioElem.onended = () => {
                    recordBtn.disabled = false;
                    feedbackButton.disabled = false; // AIが話し終わったらフィードバックボタンも有効化
                    statusMessageElem.textContent = '録音可能です。';
                };

            } else {
                aiMessageElem.textContent = '面接開始エラー: ' + (data.error || '不明なエラー');
                statusMessageElem.textContent = 'エラーが発生しました。';
                startInterviewBtn.disabled = false;
            }
        } catch (error) {
            console.error('面接開始エラー（fetchまたはJSONパース失敗）:', error);
            aiMessageElem.textContent = 'サーバーとの通信に失敗しました。';
            statusMessageElem.textContent = 'エラーが発生しました。';
            startInterviewBtn.disabled = false;
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
            feedbackButton.disabled = true; // 録音中はフィードバックボタンを無効化
            statusMessageElem.textContent = '録音中...';
            userTranscriptElem.textContent = '（録音中...）';
            aiMessageElem.textContent = 'AI: （あなたの回答を待っています）'; // AIのメッセージを更新
            aiAudioElem.style.display = 'none'; // AIの音声を非表示に
            feedbackContentElem.innerHTML = 'フィードバックを生成中...'; // フィードバックエリアを更新
        } catch (error) {
            console.error('マイクアクセスエラー:', error);
            statusMessageElem.textContent = 'マイクへのアクセスが拒否されました。';
            recordBtn.disabled = false;
            stopRecordBtn.disabled = true;
            feedbackButton.disabled = false; // エラー時はフィードバックボタンを有効に戻す
        }
    });

    // 録音停止ボタンのクリックイベント
    stopRecordBtn.addEventListener('click', () => {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            recordBtn.disabled = true;
            stopRecordBtn.disabled = true;
            feedbackButton.disabled = true; // 音声処理中はフィードバックボタンを無効化
            statusMessageElem.textContent = '音声を処理中...';
        }
    });

    // フィードバックボタンのクリックイベント
    feedbackButton.addEventListener('click', async () => {
        feedbackButton.disabled = true; // フィードバック生成中はボタンを無効化
        feedbackContentElem.innerHTML = 'フィードバックを生成中...少々お待ちください。';
        try {
            const response = await fetch('/get_feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ conversation_history: getConversationHistoryText() })
            });
            const data = await response.json();
            if (data.status === 'success') {
                feedbackContentElem.innerHTML = formatFeedback(data.feedback, data.score); // スコアも渡す
            } else {
                feedbackContentElem.textContent = 'フィードバックの取得中にエラーが発生しました: ' + (data.error || '不明なエラー');
            }
        } catch (error) {
            console.error('フィードバック取得エラー:', error);
            feedbackContentElem.textContent = 'フィードバックの取得中にサーバーとの通信エラーが発生しました。';
        } finally {
            feedbackButton.disabled = false; // 処理が終わったらボタンを有効に戻す
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
                body: JSON.stringify({ audio_data: base64data, voice_gender: voiceGenderSelect.value }) // 音声性別を送信
            });

            const data = await response.json();

            if (data.status === 'success') {
                userTranscriptElem.textContent = data.recognized_text;
                aiMessageElem.textContent = data.message;
                aiAudioElem.src = 'data:audio/mp3;base64,' + data.audio;
                aiAudioElem.style.display = 'block';
                aiAudioElem.play();
                statusMessageElem.textContent = 'AIが応答しました。';

                addHistory('あなた', data.recognized_text);
                addHistory('AI', data.message);

                // 面接終了のメッセージが含まれていたら面接を終了
                if (data.message.includes("面接は終了です")) {
                    endInterview();
                } else {
                    aiAudioElem.onended = () => {
                        recordBtn.disabled = false;
                        feedbackButton.disabled = false; // AIが話し終わったらフィードバックボタンも有効化
                        statusMessageElem.textContent = '録音可能です。';
                    };
                }

            } else {
                userTranscriptElem.textContent = data.recognized_text || '認識できませんでした。';
                aiMessageElem.textContent = 'AI応答エラー: ' + (data.message || '不明なエラー');
                statusMessageElem.textContent = 'エラーが発生しました。';
                recordBtn.disabled = false;
                feedbackButton.disabled = false; // エラー時はフィードバックボタンを有効に戻す
            }
        } catch (error) {
            console.error('音声処理エラー:', error);
            statusMessageElem.textContent = '音声処理中にエラーが発生しました。';
            recordBtn.disabled = false;
            feedbackButton.disabled = false;
        }
    }

    // 会話履歴に追加するヘルパー関数
    function addHistory(role, text) {
        const entryDiv = document.createElement('div');
        entryDiv.classList.add('entry', role.toLowerCase());
        entryDiv.innerHTML = `<span class="role">${role}:</span> ${text}`;
        historyLogElem.appendChild(entryDiv);
        historyLogElem.scrollTop = historyLogElem.scrollHeight; // スクロールを一番下へ
    }

    // 面接終了処理
    async function endInterview() {
        recordBtn.disabled = true;
        stopRecordBtn.disabled = true;
        feedbackButton.disabled = true; // 最終フィードバック生成中は無効化
        startInterviewBtn.disabled = false; // 面接終了後は再開可能に

        statusMessageElem.textContent = '面接が終了しました。フィードバックを生成中...';
        aiMessageElem.textContent = '面接は終了です。フィードバックを生成しています。'; // AIメッセージを更新

        try {
            const response = await fetch('/get_feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ conversation_history: getConversationHistoryText() })
            });
            const data = await response.json();
            if (data.status === 'success') {
                feedbackContentElem.innerHTML = formatFeedback(data.feedback, data.score); // スコアも渡す
            } else {
                feedbackContentElem.textContent = 'フィードバックの取得中にエラーが発生しました: ' + (data.error || '不明なエラー');
            }
        } catch (error) {
            console.error('最終フィードバック取得エラー:', error);
            feedbackContentElem.textContent = '最終フィードバックの取得中にサーバーとの通信エラーが発生しました。';
        } finally {
            feedbackButton.disabled = false; // 処理が終わったらボタンを有効に戻す
        }
    }

    // 会話履歴をテキスト形式で取得するヘルパー関数
    function getConversationHistoryText() {
        let historyText = "";
        const historyEntries = historyLogElem.querySelectorAll('.entry');
        historyEntries.forEach(entry => {
            const role = entry.querySelector('.role').textContent;
            const text = entry.textContent.replace(role, '').trim();
            historyText += `${role} ${text}\n`;
        });
        return historyText;
    }

    // フィードバックをカテゴリ分けして表示する関数 (スコア表示対応)
    function formatFeedback(feedbackText, score) {
        let formattedHtml = '';
        const categories = {
            "良かった点": [],
            "改善点": [],
            "総合評価": []
        };

        // フィードバックテキストからスコア部分を削除して処理
        let cleanFeedbackText = feedbackText;
        const scoreMatch = feedbackText.match(/評価点数:\s*\d+\/100/);
        if (scoreMatch) {
            cleanFeedbackText = feedbackText.replace(scoreMatch[0], '').trim();
        }

        // フィードバックテキストをカテゴリに分割
        const lines = cleanFeedbackText.split('\n');
        let currentCategory = null;
        lines.forEach(line => {
            line = line.trim();
            if (line.startsWith('良かった点:')) {
                currentCategory = "良かった点";
                categories[currentCategory].push(line.replace('良かった点:', '').trim());
            } else if (line.startsWith('改善点:')) {
                currentCategory = "改善点";
                categories[currentCategory].push(line.replace('改善点:', '').trim());
            } else if (line.startsWith('総合評価:')) {
                currentCategory = "総合評価";
                categories[currentCategory].push(line.replace('総合評価:', '').trim());
            } else if (line.startsWith('返答例:')) { // 返答例は改善点に含める
                if (categories["改善点"].length > 0) {
                    categories["改善点"][categories["改善点"].length - 1] += "\n" + line; // 直前の改善点に追加
                } else {
                    // もし返答例が単独で来た場合（通常はありえないが念のため）
                    categories["改善点"].push(line);
                }
            }
            else if (currentCategory && line) {
                categories[currentCategory].push(line);
            }
        });

        // スコアがあれば最初に表示
        if (score !== null && score !== undefined) {
            formattedHtml += `<div class="feedback-score">評価点数: ${score}/100</div>`;
        }

        // HTMLに整形
        for (const category in categories) {
            if (categories[category].length > 0) {
                formattedHtml += `<div class="feedback-category">${category}</div>`;
                categories[category].forEach(item => {
                    // 返答例のフォーマット
                    if (category === "改善点" && item.includes("返答例:")) {
                        const parts = item.split('返答例:');
                        formattedHtml += `<p>${parts[0].trim()}</p>`;
                        formattedHtml += `<p class="feedback-example">返答例: ${parts[1].trim()}</p>`;
                    } else {
                        formattedHtml += `<p>${item}</p>`;
                    }
                });
            }
        }
        return formattedHtml;
    }
});
