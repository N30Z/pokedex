FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY import.py .
COPY loop.sh .
RUN chmod +x loop.sh

CMD ["python", "import.py"]
