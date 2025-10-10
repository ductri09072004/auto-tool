# Python Test API

Dự án API test đơn giản sử dụng Flask để trả về dữ liệu "hello".

## Cài đặt

1. Cài đặt dependencies:
```bash
pip install -r requirements.txt
```

## Chạy ứng dụng

```bash
python app.py
```

Server sẽ chạy tại: `http://localhost:5001`

## Deploy (Windows/Production)

### 1) Virtualenv + Waitress
```bash
cd E:\Study\Python_test2
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install waitress
waitress-serve --host=0.0.0.0 --port=5001 app:app
```

Mở firewall (nếu cần):
```powershell
New-NetFirewallRule -DisplayName "PythonTest2_5001" -Direction Inbound -Protocol TCP -LocalPort 5001 -Action Allow
```

### 2) Docker
Dockerfile (đặt cạnh `app.py`):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install waitress
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 5001
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5001", "app:app"]
```

Build & run:
```bash
docker build -t python-test2-api .
docker run -d -p 5001:5001 --name python-test2-api python-test2-api
```

## API Endpoints

### 1. Hello World
- **URL**: `/`
- **Method**: `GET`
- **Response**:
```json
{
  "message": "Hello World!",
  "status": "success",
  "data": "Xin chào từ Python API!"
}
```

### 2. Hello API
- **URL**: `/api/hello`
- **Method**: `GET`
- **Response**:
```json
{
  "message": "Hello from API!",
  "status": "success",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 3. Health Check
- **URL**: `/health`
- **Method**: `GET`
- **Response**:
```json
{
  "status": "healthy",
  "service": "Python Test API"
}
```

## Test API

Bạn có thể test API bằng cách:

1. Mở trình duyệt và truy cập: `http://localhost:5001`
2. Sử dụng curl:
```bash
curl http://localhost:5001
curl http://localhost:5001/api/hello
curl http://localhost:5001/health
```

## Cấu trúc dự án

```
Python_test2/
├── app.py              # File chính chứa Flask API
├── requirements.txt    # Dependencies
└── README.md          # Hướng dẫn sử dụng
```
