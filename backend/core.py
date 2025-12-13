
import json
import logging
import shutil
import subprocess
import threading
import queue
import time
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import re

# Configurar logger localmente para este módulo
logger = logging.getLogger("downloader.core")

class WebSocketLogHandler(logging.Handler):
    def __init__(self, broadcast_func):
        super().__init__()
        self.broadcast_func = broadcast_func

    def emit(self, record):
        try:
            msg = self.format(record)
            # We broadcast a "log" event
            if self.broadcast_func:
                self.broadcast_func("log", msg)
        except Exception:
            self.handleError(record)

class DownloaderManager:
    def __init__(self, config_path, output_dir=None, broadcast_func=None):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir) if output_dir else None
        self.broadcast_func = broadcast_func
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # Setup WS Logger if broadcast function is provided
        if self.broadcast_func:
            ws_handler = WebSocketLogHandler(self.broadcast_func)
            ws_handler.setLevel(logging.INFO)
            # Create a simple formatter that doesn't duplicate timestamp since frontend handles it?
            # Or just raw message. Let's keep it simple.
            formatter = logging.Formatter('%(message)s')
            ws_handler.setFormatter(formatter)
            logger.addHandler(ws_handler)
            
        # Global status for UI
        self.status = {
            "state": "idle", # idle, downloading, error
            "current_song": None,
            "total_songs": 0,
            "downloaded": 0,
            "playlist_name": None
        } 
        self.config = {}
        self.reload_config()
        
        # Si no se pasó output_dir en init, usar el del config
        if not self.output_dir:
            self.output_dir = Path(self.config.get("output_dir", "./downloads"))
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verify_dependencies()

    def update_status(self, key, value):
        """Helper to update status and broadcast change."""
        self.status[key] = value
        if self.broadcast_func:
            self.broadcast_func("status", self.status)

    def reload_config(self):
        """Recarga la configuración desde el archivo JSON."""
        if not self.config_path.exists():
            # Config por defecto si no existe
            self.config = {
                "output_dir": "./downloads",
                "default_tool": "spotdl",
                "concurrency": 2,
                "retry": {"attempts": 1, "backoff_seconds": 5},
                "spotdl_extra_args": [],
                "ytdlp_extra_args": []
            }
            logger.warning(f"Config no encontrada en {self.config_path}, usando defaults.")
        else:
            try:
                self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.error(f"Error parseando config: {e}")
                raise

    def verify_dependencies(self):
        """Verifica que spotdl y yt-dlp existan y configura spotdl."""
        for tool in ["spotdl", "yt-dlp", "ffmpeg"]:
            if not shutil.which(tool):
                logger.critical(f"Herramienta faltante: {tool}")
        
        try:
            # Check ffmpeg
            subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Crear config de SpotDL (Basic)
            # We no longer manage credentials or lyrics provider here
            # SpotDL will use its default config or environment variables for credentials.
            # We still ensure the config directory exists, as SpotDL might write to it.
            config_path = Path.home() / ".config" / "spotdl" / "config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directorio de configuración de SpotDL asegurado: {config_path.parent}")
                    
        except Exception as e:
            logger.warning(f"Error general verificando dependencias: {e}")

    def _run_cmd(self, cmd):
        cmd_str = ' '.join(cmd)
        logger.debug(f"[CMD] {cmd_str}")
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out_lines = []
        try:
            for line in proc.stdout:
                line = line.strip()
                if line:
                    # ANSI Colors for nicer logs
                    C_GREEN = "\033[92m"
                    C_CYAN = "\033[96m"
                    C_YELLOW = "\033[93m"
                    C_RED = "\033[91m"
                    C_RESET = "\033[0m"

                    # Auto-recover from rate limit state if new output appears
                    if self.status["state"] == "retrying" and "rate/request limit" not in line:
                         self.status["state"] = "downloading"
                         self.status["current_song"] = "Reanudando..."

                    # Parsing logic
                    
                    # 1. Start Downloading
                    if "Downloading" in line:
                        clean = line.replace("Downloading", "").strip().replace('"', '')
                        self.status["current_song"] = clean
                        self.status["state"] = "downloading"
                        logger.info(f"{C_CYAN}⬇ INICIANDO: {clean}{C_RESET}")
                    
                    # 2. Finished Downloading (Regex for 'Downloaded "Title": url')
                    # Log line example: Downloaded "Title": https://...
                    elif "Downloaded" in line:
                         match = re.search(r'Downloaded "(.+?)"', line)
                         song_name = match.group(1) if match else "Canción"
                         
                         self.status["downloaded"] += 1
                         self.status["current_song"] = f"✔ {song_name}"
                         self.status["state"] = "downloading" # Ensure active state
                         logger.info(f"{C_GREEN}✔ COMPLETADO: {song_name}{C_RESET}")
                    
                    # 3. Skipping
                    elif "Skipping" in line:
                        clean = line.replace("Skipping", "").strip().replace('"', '')
                        self.status["current_song"] = f"⏭ Saltando: {clean}"
                        self.status["downloaded"] += 1 
                        logger.info(f"{C_YELLOW}⏭ SALTANDO: {clean}{C_RESET}")
                        
                    # 4. Total Songs
                    elif "Found" in line and "songs" in line:
                         parts = line.split()
                         for p in parts:
                             if p.isdigit():
                                 val = int(p)
                                 if val > 0:
                                     self.status["total_songs"] = val
                                 break
                         logger.info(f"{C_CYAN}📊 TOTAL ENCONTRADO: {self.status['total_songs']} canciones{C_RESET}")
                    
                    # 5. Rate Limit
                    elif "rate/request limit" in line:
                        wait_time = "un momento"
                        match = re.search(r"after:\s*(\d+)", line)
                        if match:
                            wait_time = f"{match.group(1)}s"
                        
                        self.status["current_song"] = f"⏳ Límite de API (Reintentando en {wait_time}...)"
                        self.status["state"] = "retrying"
                        logger.warning(f"{C_RED}⚠ RATE LIMIT: Esperando {wait_time}{C_RESET}")
                        
                    # 6. Fallback logging for other lines (muted)
                    else:
                        logger.debug(f"STDOUT: {line}")

                    # Broadcast status update if something changed
                    if self.broadcast_func:
                        self.broadcast_func("status", self.status)

        except Exception as e:
            proc.kill()
            raise e
        
        proc.wait()
        if proc.returncode != 0:
            logger.error(f"Fallo comando: {cmd_str}")
            return False, out_lines
        return True, out_lines

    def _download_worker(self, q, results):
        retry_cfg = self.config.get("retry", {"attempts": 1, "backoff_seconds": 5})
        max_att = retry_cfg.get("attempts", 1)

        while True:
            item = q.get()
            if item is None:
                break
            
            # Unpack item (supports optional m3u_name)
            if len(item) == 3:
                url, tool, m3u_name = item
            else:
                url, tool = item
                m3u_name = None

            attempts = 0
            success = False
            
            extra_args = self.config.get(f"{tool}_extra_args", [])
            
            # Construir comando
            if tool == "spotdl":
                # Usar sync para mantener estado
                import hashlib
                sync_dir = self.output_dir / ".sync"
                sync_dir.mkdir(exist_ok=True)
                
                url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
                save_file = sync_dir / f"{url_hash}.spotdl"
                
                # Pre-load stats from existing sync file if possible
                try:
                    if save_file.exists():
                        data = json.loads(save_file.read_text(encoding='utf-8'))
                        if "songs" in data:
                            self.status["total_songs"] = len(data["songs"])
                        if "name" in data:
                            self.status["playlist_name"] = data["name"]
                        logger.info(f"Stats precargados de sync file: {self.status['total_songs']} canciones")
                except Exception as e:
                    logger.warning(f"No se pudo leer sync file: {e}")

                # Obtener formato y bitrate
                fmt = self.config.get("format", "mp3")
                bitrate = "auto"
                
                # Determine m3u filename
                if m3u_name:
                    # Sanitize simple filename
                    safe_name = "".join(c for c in m3u_name if c.isalnum() or c in (' ', '-', '_')).strip()
                    m3u_arg = f"{self.output_dir}/{safe_name}.m3u8"
                else:
                    m3u_arg = f"{self.output_dir}/{{list[0]}}.m3u8"

                # Prepare base command
                lyrics_provider = self.config.get("lyrics_provider", "genius")
                
                cmd = [
                    "spotdl", "sync", url, 
                    "--save-file", str(save_file), 
                    "--output", str(self.output_dir),
                    "--format", fmt,
                    "--bitrate", bitrate,
                    "--m3u", m3u_arg # Always add our m3u arg first
                ]
                cmd.extend(extra_args) # Then add extra args, which can override if they contain --m3u
            else:
                cmd = ["yt-dlp", url, "-P", str(self.output_dir)]
            
            # Set state to running for this url
            self.status["state"] = "processing"
            
            while attempts < max_att:
                attempts += 1
                logger.info(f"Descargando {url} con {tool} (Intento {attempts})")
                
                success, logs = self._run_cmd(cmd)
                
                if success:
                    # Post-process M3U8 to fix paths
                    if tool == "spotdl" and m3u_name: # Only for spotdl and if m3u_name was provided
                        try:
                            # m3u_arg is the full path to the m3u8 file
                            m3u_file = Path(m3u_arg)
                            if m3u_file.exists():
                                content = m3u_file.read_text(encoding='utf-8')
                                
                                new_lines = []
                                for line in content.splitlines():
                                    if line.startswith("#") or not line.strip():
                                        new_lines.append(line)
                                        continue
                                        
                                    # It's a file path
                                    p = Path(line)
                                    # Force simple filename relative to current directory
                                    filename = p.name
                                    new_lines.append(f"./{filename}")
                                
                                m3u_file.write_text("\n".join(new_lines), encoding='utf-8')
                                logger.info(f"Corregidas rutas en M3U: {m3u_file}")
                        except Exception as e:
                            logger.error(f"Error procesando M3U: {e}")
                            
                    results.append({"url": url, "status": "success", "attempts": attempts})
                    break # Exit retry loop
                else:
                    logger.warning(f"Error en intento {attempts}. Salida:\n" + "\n".join(logs[-10:]))
                    if attempts < max_att:
                        time.sleep(retry_cfg.get("backoff_seconds", 5))
                    else:
                        logger.error(f"Fallo final para {url}.")
                        results.append({"url": url, "status": "failed", "attempts": attempts, "error_log": lines[-10:]})
            
            q.task_done()

    def determine_tool(self, url):
        # Lógica de decisión
        if "spotify" in url:
            return "spotdl"
        elif "youtube" in url or "youtu.be" in url:
            return "yt-dlp"
        
        # Fallback a default config
        if ("playlist" in url) or ("spotify" in url):
             return "spotdl"
        return self.config.get("default_tool", "spotdl")

    def process_urls(self, urls, m3u_name=None):
        """Procesa una lista de URLs en paralelo.
        
        Args:
            urls: Lista de URLs a descargar
            m3u_name: Nombre opcional para el archivo m3u8 (solo spotdl)
        """
        concurrency = self.config.get("concurrency")
        if not concurrency or not isinstance(concurrency, int):
            concurrency = 2
            
        q = queue.Queue()
        results = []
        
        tasks = []
        for u in urls:
            t = self.determine_tool(u)
            tasks.append((u, t, m3u_name))
            
        # Init status
        self.status["state"] = "starting"
        self.status["total_songs"] = 0 # Reset count for new batch
        self.status["downloaded"] = 0
        if self.broadcast_func: self.broadcast_func("status", self.status)
            
        for t in tasks:
            q.put(t)
            
        threads = []
        for _ in range(concurrency):
            th = threading.Thread(target=self._download_worker, args=(q, results), daemon=True)
            th.start()
            threads.append(th)
            
        q.join()
        for _ in threads:
            q.put(None)
        for th in threads:
            th.join()
            
        # Reset status to idle when done
        self.status["state"] = "idle"
        self.status["current_song"] = None
        if self.broadcast_func: self.broadcast_func("status", self.status)
        
        return results
