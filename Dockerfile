FROM python:3.10.19-slim

WORKDIR /app

# Install system dependencies (ffmpeg, nodejs for yt-dlp)
RUN apt-get update && apt-get install -y ffmpeg nodejs && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (caching)
COPY backend/requirements.txt .
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy Backend Code
COPY backend/ /app/

# Copy Frontend Assets
COPY frontend/ /app/frontend/

# Create directories for persistence
RUN mkdir -p /app/downloads /app/config /app/data && \
    chmod 777 /app/downloads /app/config /app/data

# Security: Run as non-root user (switch back if strictly needed, 
# but user requested 0:0 in compose. For the image itself, we can default to appuser 
# but compose overrides it. Let's keep the setup ready for rootless if possible, 
# but allow override).
# Note: The user explicitly demanded running as root in compose to fix permission errors.
# We will create the user but NOT switch to it by default in the image to avoid confusion 
# unless we are sure.
# Actually, standard practice is to switch. But given the history of permission issues,
# let's comment out the USER switch and let compose handle it with user: "0:0" or similar.
# Update: User approved "All-in-One".
# Let's create the user but leave USER instruction off or use root for now to match 
# the "it works" state, OR we set it and user invalidates it in compose.
# The previous Dockerfile had USER appuser. The compose had user: "0:0".
# So the compose OVERRIDES the image user. We will keep USER appuser in the Dockerfile
# as a best practice default, knowing the user overrides it in Compose.

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
