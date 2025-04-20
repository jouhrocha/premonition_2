# Dockerfile
FROM python:3.11-slim as builder
WORKDIR /app
COPY . /app
COPY requirements.txt .
COPY . .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt
ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]