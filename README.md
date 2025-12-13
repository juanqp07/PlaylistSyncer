# OpusVault 🎵

A self-hosted, Dockerized music downloader and manager. Automatically syncs playlists from Spotify and YouTube, downloading them in high-quality Opus (or configurable) format using `spotdl` and `yt-dlp`. Features a modern web interface for management.

![OpusVault UI](https://via.placeholder.com/800x400?text=OpusVault+Dashboard)

## Features

- 🐳 **Dockerized**: Easy to deploy with a single command.
- 🎹 **Spotify & YouTube Support**: Downloads playlists and tracks seamlessly.
- 🎛️ **Web Interface**: Manage playlists, view downloads, and configure settings from your browser.
- 🔒 **Secure**: handling of API credentials via environment variables.
- ⚡ **Efficient**: Uses `spotdl` sync logic to download only new tracks.
- 📂 **Organized**: Downloads are saved to a volume-mapped directory.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/opusvault.git
    cd opusvault
    ```

2.  **Configure Environment**:
    Copy the example environment file and add your Spotify credentials (required to avoid rate limits).
    ```bash
    cp env.example .env
    ```
    Edit `.env` and fill in your keys:
    ```ini
    SPOTIFY_CLIENT_ID=your_id
    SPOTIFY_CLIENT_SECRET=your_secret
    ```
    > ℹ️ *You can get these keys from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).*

3.  **Start the Application**:
    ```bash
    docker-compose up -d --build
    ```

4.  **Access the UI**:
    Open your browser and navigate to:
    [http://localhost:80](http://localhost:80)

## Usage

1.  **Add Playlist**: Paste a Spotify or YouTube playlist URL in the "Añadir Playlist" field.
2.  **Download**: Click "Ejecutar Ahora" to start the sync process.
3.  **Monitor**: Watch the status update in real-time.
4.  **View Tracks**: Click "Ver Tracks" on any playlist to see what has been downloaded.

## Configuration

You can adjust settings via the Web UI:
- **Audio Format**: `opus`, `mp3`, `flac`, etc.
- **Bitrate**: Target bitrate (e.g., `128k`, `320k`).
- **Concurrency**: Number of simultaneous downloads.

*Note: The download directory is locked to `/app/downloads` inside the container.*

## Troubleshooting

- **Check Logs**:
    ```bash
    docker logs -f opusvault
    ```
- **Permissions**: Ensure the `downloads` folder on your host is writable.

## License

MIT
