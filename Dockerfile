# Pythonの公式軽量イメージをベースにする
FROM python:3.9-slim-buster

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピー
COPY requirements.txt .

# 依存関係をインストール
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . .

# 環境変数PORTが設定されていない場合のデフォルトポート
ENV PORT=8080

# ポートを公開
EXPOSE 8080

# アプリケーションを実行
# Flaskの開発サーバーは本番環境には不向きなので、GunicornなどのWSGIサーバーを使うのが一般的ですが
# Cloud Runはリクエスト駆動でスケールするため、軽量なFlask内蔵サーバーでも動作可能です
# 小規模な無料枠運用であればFlask内蔵サーバーで問題ありません
CMD ["python", "app.py"]
