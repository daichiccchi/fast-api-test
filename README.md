# Cross-Account AWS Access Test API

EC2からクロスアカウントでAPI GatewayとS3にアクセスするためのテストAPIサーバー

## 機能

- `/apigw` - API GatewayへのSigV4署名付きリクエスト
- `/bucket` - S3へのファイルアップロード
- `/test-credentials` - AWS認証情報の確認

## セットアップ

### ローカル環境での実行

```bash
# Docker Composeで起動
docker-compose up --build

# または直接Pythonで実行
pip install -r requirements.txt
uvicorn app:app --reload
```

### EC2へのデプロイ

1. EC2インスタンスにDockerとDocker Composeをインストール

```bash
sudo yum update -y
sudo yum install -y docker
sudo service docker start
sudo usermod -a -G docker ec2-user

# Docker Composeのインストール
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

2. コードをEC2にコピー

```bash
# ローカルから
scp -r ./* ec2-user@<EC2_IP>:/home/ec2-user/api-server/
```

3. EC2上で起動

```bash
cd /home/ec2-user/api-server
docker-compose up -d
```

## 使用方法

### API Gatewayへのアクセステスト

```bash
curl -X POST http://localhost:8000/apigw \
  -H "Content-Type: application/json" \
  -d '{
    "api_gateway_url": "https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/prod/your-endpoint",
    "method": "GET",
    "region": "ap-northeast-1",
    "assume_role_arn": "arn:aws:iam::123456789012:role/YourCrossAccountRole"
  }'
```

### S3へのファイルアップロードテスト

```bash
curl -X POST http://localhost:8000/bucket \
  -F "file=@test.txt" \
  -F 'request={
    "bucket_name": "your-bucket-name",
    "object_key": "test/file.txt",
    "region": "ap-northeast-1",
    "assume_role_arn": "arn:aws:iam::123456789012:role/YourCrossAccountRole"
  }'
```

### 認証情報の確認

```bash
curl http://localhost:8000/test-credentials
```

## トラブルシューティング

### 403エラーが発生する場合

1. **IAMロールの信頼関係を確認**
   - AssumeRoleを実行するEC2のロールが信頼されているか確認

2. **API Gatewayのリソースポリシー確認**
   - クロスアカウントアクセスが許可されているか確認

3. **SigV4署名の確認**
   - `/apigw`エンドポイントのレスポンスで`request_headers_sent`を確認
   - Authorization ヘッダーが正しく設定されているか確認

## 環境変数

- `AWS_DEFAULT_REGION` - デフォルトリージョン（デフォルト: ap-northeast-1）
- `ASSUME_ROLE_ARN` - クロスアカウントアクセス用のロールARN（オプション）

※ EC2インスタンスプロファイルを使用するため、AWS認証情報の環境変数は不要です