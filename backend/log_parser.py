
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

        # 3. SpotDL Skipping (Duplicate)
        elif "Skipping" in line and tool == "spotdl":
             clean = line.replace("Skipping", "", 1).strip()
             # Remove "(file already exists) (duplicate)"
             clean = clean.replace("(file already exists)", "").replace("(duplicate)", "").strip()
             
             if "http" not in clean: 
                 updates["current_song"] = clean
                 updates["downloaded_increment"] = 1 # Count duplicates as processed!
                 updates["log_message"] = f"{C_GREEN}✔ Ya existe: {clean}{C_RESET}"

        # 4. Rate Limits (Friendly)
        elif "rate/request limit" in line:
            wait_time = "un momento"
            match = re.search(r"after:\s*(\d+)", line)
            if match:
                wait_time = f"{match.group(1)}s"
            
            updates["state"] = "retrying"
            updates["log_message"] = f"{C_YELLOW}⏳ Límite de Spotify. Esperando {wait_time}...{C_RESET}"
            updates["log_level"] = "warning"

        # 5. Success (SpotDL)
        elif "Downloaded" in line and tool == "spotdl":
            match = re.search(r'Downloaded "(.+?)"', line)
            song_name = match.group(1) if match else "Canción"
            updates["downloaded_increment"] = 1
            updates["current_song"] = f"✔ {song_name}"
            updates["log_message"] = f"{C_GREEN}✔ Completado: {song_name}{C_RESET}"
        
        # 5b. SpotDL Lookup Error
        elif "LookupError" in line and "No results found" in line:
            updates["downloaded_increment"] = 1
            # "LookupError: No results found for song: Rauw Alejandro - LOKERA"
            clean = line.split("song:", 1)[-1].strip()
            updates["log_message"] = f"{C_RED}❌ No encontrado en YouTube: {clean}{C_RESET}"

        # 6. Already Downloaded
        elif "has already been downloaded" in line:
             # Try to extract title
             song_name = "Canción"
             if "downloads/" in line:
                 try: 
                    # Extract filename part
                    raw_name = line.split("downloads/")[1]
                    # Remove the suffix
                    clean_name = raw_name.replace(" has already been downloaded", "")
                    # Remove extension
                    if "." in clean_name:
                        clean_name = clean_name.rsplit(".", 1)[0]
                    song_name = clean_name
                 except: pass
             
             # Don't increment here if YT-DLP "Downloading item" already counted total?
             # YT-DLP items are confusing. Usually "Downloading item x of y" is the start.
             # "has already been" is the result. So yes, increment.
             updates["downloaded_increment"] = 1
             updates["log_message"] = f"{C_GREEN}✔ Ya existe: {song_name}{C_RESET}"

        # 7. YT-DLP Item Progress
        elif "Downloading item" in line and "of" in line:
             match = re.search(r"Downloading item (\d+) of (\d+)", line)
             if match:
                 current = int(match.group(1))
                 total = int(match.group(2))
                 updates["total_songs"] = total
                 updates["current_song"] = f"Procesando {current}/{total}"
                 updates["log_message"] = f"{C_CYAN}🎵 Procesando canción {current} de {total}{C_RESET}"

        # 7b. YT-DLP Destination (Filename) capture
        elif "[download] Destination:" in line:
             # Extract filename
             try:
                 parts = line.split("Destination:")[1].strip()
                 # Remove path
                 if "/" in parts: parts = parts.rsplit("/", 1)[1]
                 # Remove ext
                 if "." in parts: parts = parts.rsplit(".", 1)[0]
                 
                 updates["current_song"] = parts
                 updates["state"] = "downloading"
                 updates["log_message"] = f"{C_CYAN}⬇ Descargando: {parts}{C_RESET}"
             except: pass

        # 8. YT-DLP Warnings
        elif "WARNING:" in line:
            clean = line.split("WARNING:")[1].strip()
            
            if ("SABR streaming" in clean or 
                "web_safari client" in clean or 
                "web client" in clean or
                "missing a url" in clean or
                "JavaScript runtime" in clean): 
                return {} 
            
            # If warning is about error in attempt, ignore safely as we handle retries
            if "Error en intento" in clean:
                return {}

            updates["log_message"] = f"{C_YELLOW}⚠ {clean}{C_RESET}"
            updates["log_level"] = "warning"

        # 9. YT-DLP Errors
        elif "ERROR:" in line or "PermissionError" in line or "AudioProviderError" in line:
             clean = line.replace("ERROR:", "").replace("downloader.core:", "").strip()
             increment = 0
             
             if "PermissionError" in line:
                 clean = "Error de permisos (No se puede escribir en disco)"
             elif "AudioProviderError" in line:
                 # Clean up the spotdl wrapper error
                 clean = clean.replace("AudioProviderError:", "").strip()
                 if "YT-DLP download error" in clean:
                     clean = "Error de YT-DLP (Posible bloqueo o login requerido)"
             elif "Video unavailable" in clean:
                 clean = "Vídeo no disponible"
                 increment = 1 # Count unavailable videos as processed (failed)
             elif "fragment" in clean:
                 increment = 0 # Fragment errors usually retry
             
             if increment > 0:
                 updates["downloaded_increment"] = increment
                 
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
