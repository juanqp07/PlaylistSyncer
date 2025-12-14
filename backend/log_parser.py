
import re
import logging

# ANSI Colors
C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_RESET = "\033[0m"

logger = logging.getLogger("downloader.parser")

class LogParser:
    """Parses stdout lines from spotdl and yt-dlp to extract structured status info."""
    
    def __init__(self):
        pass

    def parse(self, line: str, tool: str, current_state: str) -> dict:
        """
        Parses a log line and returns a dict with status updates.
        Returns empty dict if no significant status change found.
        
        Keys in return dict:
        - state: str (new state)
        - current_song: str
        - downloaded_increment: int (1 if a song finished)
        - total_songs: int
        - log_message: str (formatted info message to log)
        - log_level: str ("info", "warning", "error")
        - log_raw: str (if we want to force raw log broadcast)
        """
        updates = {}
        line = line.strip()
        if not line:
            return updates

        # 1. SpotDL Start / Found
        if "Found" in line and "songs in" in line:
            # Flexible regex for "Found 50 songs in PlaylistName"
            match = re.search(r"Found (\d+) songs in (.+)", line)
            if match:
                try:
                    count = int(match.group(1))
                    name = match.group(2).replace("(Playlist)", "").strip()
                    # ANSI cleanup for name just in case
                    name = re.sub(r'\x1b\[[0-9;]*m', '', name) 
                    
                    updates["total_songs"] = count
                    updates["log_message"] = f"{C_CYAN}📊 Playlist detectada: {name} ({count} canciones){C_RESET}"
                except:
                    pass

        # 2. SpotDL Downloading
        elif "Downloading" in line and tool == "spotdl":
            clean = line.replace("Downloading", "").strip().replace('"', '')
            if "http" not in clean: # avoid "Downloading https://..." urls
                updates["current_song"] = clean
                updates["state"] = "downloading"
                updates["log_message"] = f"{C_CYAN}⬇ Descargando: {clean}{C_RESET}"

        # 3. SpotDL Skipping
        elif "Skipping" in line and tool == "spotdl":
            clean = line.replace("Skipping", "").strip().replace('"', '')
            if "http" not in clean: # avoid "Downloading https://..." urls
                updates["current_song"] = clean
                updates["state"] = "skipping"
                updates["log_message"] = f"{C_CYAN}⏭️ Saltando: {clean}{C_RESET}"
        # 4. Rate Limits (Friendly)
        elif "rate/request limit" in line:
            wait_time = "un momento"
            match = re.search(r"after:\s*(\d+)", line)
            if match:
                wait_time = f"{match.group(1)}s"
            
            updates["state"] = "retrying"
            # Friendly message
            updates["log_message"] = f"{C_YELLOW}⏳ Límite de Spotify. Esperando {wait_time}...{C_RESET}"
            updates["log_level"] = "warning"

        # 5. Success (SpotDL)
        elif "Downloaded" in line and tool == "spotdl":
            match = re.search(r'Downloaded "(.+?)"', line)
            song_name = match.group(1) if match else "Canción"
            updates["downloaded_increment"] = 1
            updates["current_song"] = f"✔ {song_name}"
            updates["log_message"] = f"{C_GREEN}✔ Completado: {song_name}{C_RESET}"

        # 6. Already Downloaded
        elif "has already been downloaded" in line:
             # Try to extract title
             song_name = "Canción"
             if "downloads/" in line:
                 try: 
                    parts = line.split("downloads/")[1].split(" [")
                    song_name = parts[0]
                 except: pass
             
             updates["downloaded_increment"] = 1
             updates["log_message"] = f"{C_GREEN}✔ Ya existe: {song_name}{C_RESET}"

        # 7. YT-DLP Item Progress
        elif "Downloading item" in line and "of" in line:
             match = re.search(r"Downloading item (\d+) of (\d+)", line)
             if match:
                 current = int(match.group(1))
                 total = int(match.group(2))
                 updates["total_songs"] = total
                 updates["log_message"] = f"{C_CYAN}🎵 Procesando canción {current} de {total}{C_RESET}"

        # 8. YT-DLP Warnings (JS Runtime, etc)
        elif "WARNING:" in line:
            clean = line.split("WARNING:")[1].strip()
            
            # Suppress noisy SABR/WebClient warnings and JS Runtime warnings
            if ("SABR streaming" in clean or 
                "web_safari client" in clean or 
                "web client" in clean or
                "missing a url" in clean or
                "JavaScript runtime" in clean): # Silence the "No supported JavaScript runtime" warning
                return {} # Skip entirely
                
            updates["log_message"] = f"{C_YELLOW}⚠ {clean}{C_RESET}"
            updates["log_level"] = "warning"

        # 9. YT-DLP Errors
        elif "ERROR:" in line or "PermissionError" in line:
             clean = line.replace("ERROR:", "").replace("downloader.core:", "").strip()
             if "PermissionError" in line:
                 clean = "Error de permisos (No se puede escribir en disco)"
             elif "Video unavailable" in clean:
                 clean = "Vídeo no disponible"
             
             updates["log_message"] = f"{C_RED}❌ Error: {clean}{C_RESET}"
             updates["log_level"] = "error"

        # 10. Skip Noise (Webpage, etc)
        elif "Downloading webpage" in line or "Extracting URL" in line:
             pass # Silent

        # 11. Generic "Processing" for YT-DLP
        elif "[download]" in line and "%" in line:
             # 23.5% of 10.00MiB at 2.00MiB/s ETA 00:05
             updates["state"] = "downloading"
             # No log message to avoid spam, frontend handles progress bar if we parsed it (TODO)
             # sending raw for "hacker console" feel? User wants easy.
             # Let's send 1 simple update every 20%? No too complex state.
             pass

        return updates
