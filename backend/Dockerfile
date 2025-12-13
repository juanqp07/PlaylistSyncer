FROM python:3.10.19-slim

WORKDIR /app

# Instalar ffmpeg (necesario para yt-dlp/spotdl)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Directorio para persistencia
RUN mkdir -p /app/downloads /app/config && chmod 777 /app/downloads /app/config

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
