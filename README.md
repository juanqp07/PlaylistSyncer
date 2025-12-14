> [!WARNING]
> Este proyecto ha sido generado enteramente usando Inteligencia Artificial. Úsalo bajo tu propia responsabilidad. La lógica de descarga y sincronización (vía `spotdl` y `yt-dlp`) depende de servicios de terceros que pueden cambiar o bloquear el acceso en cualquier momento. El autor y la IA no asumen ninguna responsabilidad por su mal uso.

# PlaylistSyncer 🎵

Un gestor y descargador de música auto-hospedado y dockerizado. Sincroniza automáticamente playlists de Spotify y YouTube, descargándolas en formato Opus de alta calidad (o configurable) usando `spotdl` y `yt-dlp`. Cuenta con una interfaz web moderna y responsiva.

## Características

- 🐳 **Todo en Uno**: Backend y Frontend en un único contenedor Docker.
- 🎹 **Spotify y YouTube**: Sincroniza playlists completas sin problemas.
- 🎛️ **Interfaz Moderna**: Progreso en tiempo real, logs detallados y panel de gestión.
- ⚡ **Sync Inteligente**: Usa `spotdl` para descargar solo las canciones nuevas.
- 🛑 **Control Total**: Detén las descargas al instante con un sistema robusto de parada.
- 🔒 **Auto-Hospedado**: Tus datos, tus reglas.

## Instalación

### Método 1: Docker Compose (Recomendado)

1.  Crea un archivo `docker-compose.yml`:

    ```yaml
    services:
      playlistsyncer:
        image: ghcr.io/juanqp07/playlistsyncer:latest
        container_name: playlistsyncer
        ports:
          - "8030:8000"
        volumes:
          - ./downloads:/app/downloads
          - ./data:/app/data
        restart: unless-stopped
    ```

2.  Arranca el contenedor:
    ```bash
    docker-compose up -d
    ```

3.  Accede a la UI en `http://localhost:8030`.

### Método 2: Construir desde el código

1.  Clona el repositorio:
    ```bash
    git clone https://github.com/tuusuario/playlistsyncer.git
    cd playlistsyncer
    ```

2.  Construye y arranca:
    ```bash
    docker-compose up -d --build
    ```

## Uso

1.  **Añadir Playlist**: Pega la URL de una playlist de Spotify o YouTube.
2.  **Sincronizar**: Haz clic en **"Sincronizar Todo"** (o en los botones individuales) para empezar.
3.  **Logs**: Observa la consola integrada con estados detallados y emojis (ej. `✨ Procesando: [Canción]`).
4.  **Stop**: Usa el botón de Stop para detener inmediatamente todas las descargas.

## Configuración

Navega a la pestaña **Ajustes** en la UI para cambiar:
- **Formato de Audio**: `opus` (por defecto), `mp3`, `flac`, etc.
- **Bitrate**: `192k` es el punto dulce entre calidad y peso.
- **Concurrencia**: Cuántas descargas ejecutar en paralelo.

## Solución de Problemas

- **Permisos**: Si las descargas fallan con errores de permisos, asegúrate de que la carpeta del host permite escritura, o ejecuta el contenedor como root (la config de compose proporcionada suele manejar esto).
- **Logs**: Revisa `docker logs -f playlistsyncer` si la UI deja de responder.

## Licencia

MIT - Úsalo libremente, ¡pero recuerda la advertencia sobre la IA!
