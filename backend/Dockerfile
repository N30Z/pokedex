FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY frontend ./static

EXPOSE 1510

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1510"]
