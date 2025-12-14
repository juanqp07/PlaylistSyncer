
import json
import logging
import shutil
import subprocess
import threading
import queue
import time
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, List, Any, Callable
import signal

# Robust Import for LogParser
try:
    from backend.log_parser import LogParser
except ImportError:
    from log_parser import LogParser

# Configurar logger localmente para este módulo
logger = logging.getLogger("downloader.core")



class DownloaderManager:
    def __init__(self, config_path: str, output_dir: Optional[str] = None, broadcast_func: Optional[Callable] = None):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir) if output_dir else None
        self.broadcast_func = broadcast_func
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.parser = LogParser()
        
        self.parser = LogParser()
        
        # Setup WS Logger removed - Manual broadcast in _run_cmd
            
        # Global status for UI
        self.status: Dict[str, Any] = {
            "state": "idle", # idle, downloading, error
            "current_song": None,
            "total_songs": 0,
            "downloaded": 0,
            "playlist_name": None
        } 
        self.config = {}
        self.reload_config()
        
        # Stop Control
        self.stop_requested = threading.Event()
        self.active_processes = set() # Track ALL running processes
        self.proc_lock = threading.Lock() # Lock for process set
        
        # Si no se pasó output_dir en init, usar el del config
        if not self.output_dir:
            self.output_dir = Path(self.config.get("output_dir", "./downloads"))
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verify_dependencies()

    def _kill_by_name(self, target_name: str):
        """Nuclear option: finds and kills any process containing target_name."""
        try:
            # Iterate over all running processes
            for pid_str in os.listdir('/proc'):
                if not pid_str.isdigit():
                    continue
                
                try:
                    pid = int(pid_str)
                    with open(f'/proc/{pid}/cmdline', 'rb') as f:
                        # cmdline arguments are separated by null bytes
                        cmd_bytes = f.read()
                        cmd = cmd_bytes.decode('utf-8', errors='ignore').replace('\0', ' ')
                        
                    if target_name in cmd:
                        logger.info(f"🧹 Limpiando proceso residual '{target_name}' (PID {pid})...")
                        os.kill(int(pid), signal.SIGKILL)
                except (ProcessLookupError, FileNotFoundError, PermissionError):
                    continue
                except Exception as e:
                    logger.error(f"Error killing PID {pid}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in nuclear kill: {e}")

    def stop(self):
        """Signals the manager to stop processing and kills active process."""
        msg = "🛑 Deteniendo descargas..."
        logger.info(msg)
        if self.broadcast_func: self.broadcast_func("log", msg)
        
        self.stop_requested.set()
        
        # Kill ALL active processes safely
        with self.proc_lock:
            if not self.active_processes:
                logger.debug("No active processes to kill via object reference.")
            
            for proc in list(self.active_processes): # Copy to avoid modification while cleaning
                try:
                    if proc.poll() is None:
                        logger.info(f"🛑 Deteniendo grupo de procesos {proc.pid}...")
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                            try:
                                proc.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        except Exception as e:
                            logger.error(f"Error killing PID {proc.pid}: {e}")
                except Exception as master_e:
                     pass
        
        # Nuclear Option: Kill by name to ensure no orphans
        self._kill_by_name("yt-dlp")
        self._kill_by_name("spotdl")
        self._kill_by_name("ffmpeg")
        
        self.update_status("state", "stopped")

    def update_status(self, key: str, value: Any):
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
        """Verifica que spotdl, yt-dlp y ffmpeg existan."""
        for tool in ["spotdl", "yt-dlp", "ffmpeg"]:
            if not shutil.which(tool):
                logger.critical(f"Herramienta faltante: {tool}")
        
        try:
            # Check ffmpeg
            subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Crear config de SpotDL (Basic)
            config_path = Path.home() / ".config" / "spotdl" / "config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
                    
        except Exception as e:
            logger.warning(f"Error general verificando dependencias: {e}")

    def _run_cmd(self, cmd: List[str]) -> tuple[bool, List[str]]:
        if self.stop_requested.is_set():
            return False, []
            
        cmd_str = ' '.join(cmd)
        logger.debug(f"[CMD] {cmd_str}")
        
        tool = "spotdl" if "spotdl" in cmd[0] else "yt-dlp"
        
        proc = None
        try:
             # Start process w/ new session for group killing
             proc = subprocess.Popen(
                 cmd, 
                 stdout=subprocess.PIPE, 
                 stderr=subprocess.STDOUT, 
                 text=True,
                 start_new_session=True 
             )
             
             with self.proc_lock:
                 self.active_processes.add(proc)
             
             out_lines = []
             while True:
                 # Check stop flag aggressively
                 if self.stop_requested.is_set():
                     logger.info("🛑 Interrupción de comando detectada.")
                     try:
                         # Ensure we kill this specific process immediately if stop is set
                         os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                     except: pass
                     break
                     
                 # Check if process ended
                 if proc.poll() is not None:
                     # Read remainder
                     rem = proc.stdout.read()
                     if rem:
                         for l in rem.splitlines():
                             if l.strip(): out_lines.append(l.strip())
                     break
                     
                 line = proc.stdout.readline()
                 
                 if not line and proc.poll() is not None:
                     break
                     
                 if not line:
                     continue
                
                 line = line.strip()
                 if line:
                     out_lines.append(line)
                     
                     # 1. PARSE FIRST
                     updates = self.parser.parse(line, tool, self.status["state"])
                     
                     # 2. LOGGING STRATEGY
                     is_error = "ERROR:" in line or "WARNING:" in line
                     has_update = bool(updates) and "log_message" in updates
                     
                     # Explicitly ignore known noisy lines
                     is_noise = (
                        "Downloading webpage" in line or 
                        "Extracting URL" in line or 
                        "m3u8 information" in line or
                        "android sdkless" in line or
                        "web safari" in line or
                        "[ExtractAudio]" in line or
                        "JavaScript runtime" in line or
                        "web_safari client" in line or
                        "web client" in line
                     )

                     if not is_noise:
                         # 2. CONSOLE LOGGING (Raw/Normal)
                         # User requested "logs normales" in console
                         logger.info(line)
                    
                     # 3. FRONTEND BROADCAST (Pretty/Modified)
                     if updates:
                         if "downloaded_increment" in updates:
                             self.status["downloaded"] += updates.pop("downloaded_increment")
                             
                         if "log_message" in updates:
                             if self.broadcast_func:
                                 # Send raw message with ANSI codes so frontend can parse colors
                                 self.broadcast_func("log", updates["log_message"])
                         
                         for k, v in updates.items():
                             if k not in ["log_message", "log_level", "log_raw"]:
                                 self.status[k] = v
                        
                         # CRITICAL: Broadcast status immediately after update
                         if self.broadcast_func:
                             self.broadcast_func("status", self.status)

             proc.wait()
             
             # Determine success
             is_success = (proc.returncode == 0)
             
             # YT-DLP Soft Success: Playlist finished but some videos were unavailable (exit code != 0)
             if not is_success and tool == "yt-dlp":
                 # Scan for explicit "Finished" message
                 if any("Finished downloading playlist" in l for l in out_lines):
                     logger.info("✅ Playlist completada (con errores de vídeos no disponibles).")
                     is_success = True
                     
             # SpotDL Soft Success: If sync file saved, we are good
             if not is_success and tool == "spotdl":
                 if any("Saved results to" in l and ".spotdl" in l for l in out_lines):
                      logger.info("✅ SpotDL finalizado correctamente (Sync guardado).")
                      is_success = True

             return is_success, out_lines
             
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            if proc:
                try:
                    proc.kill()
                except: pass
            return False, []
        finally:
            if proc:
                with self.proc_lock:
                    self.active_processes.discard(proc)

    def _download_worker(self, q: queue.Queue, results: List[Dict]):
        retry_cfg = self.config.get("retry", {"attempts": 1, "backoff_seconds": 5})
        max_att = retry_cfg.get("attempts", 1)

        while True:
            item = q.get()
            if item is None:
                q.task_done()
                break
            
            # CRITICAL: If stopped, drain the queue
            if self.stop_requested.is_set():
                q.task_done()
                continue

            # Unpack item (supports optional m3u_name)
            if len(item) == 3:
                url, tool, m3u_name = item
            else:
                url, tool = item
                m3u_name = None

            attempts = 0
            success = False
            
            extra_args = self.config.get("spotdl_extra_args", [])
        
            # Command Selection
            cmd = []
            if tool == "spotdl":
                # Construir comando (SpotDL)
                import hashlib
                sync_dir = self.output_dir / ".sync"
                sync_dir.mkdir(parents=True, exist_ok=True)
                
                url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
                save_file = sync_dir / f"{url_hash}.spotdl"
                
                # Obtener formato y bitrate
                fmt = self.config.get("format", "mp3")
                bitrate = self.config.get("bitrate", "192k")
                
                # Determine m3u filename parameter
                if m3u_name:
                    safe_name = "".join(c for c in m3u_name if c.isalnum() or c in (' ', '-', '_')).strip()
                    m3u_arg = f"{self.output_dir}/{safe_name}.m3u8"
                else:
                    m3u_arg = f"{self.output_dir}/{{list[0]}}.m3u8"

                cmd = [
                    "spotdl", "download", url, 
                    "--save-file", str(save_file), 
                    "--output", f"{self.output_dir}/{{artist}} - {{title}}",
                    "--format", fmt,
                    "--bitrate", bitrate,
                    "--restrict", "ascii", # Force ASCII filenames (Fixes RØZ -> ROZ and prevents redownloads)
                    "--m3u", m3u_arg
                ]
                
                # Check for cookies.txt
                cookies_path = self.config_path.parent / "cookies.txt"
                if cookies_path.exists():
                    cmd.extend(["--cookie-file", str(cookies_path)])
                    
                cmd.extend(extra_args)

            elif tool == "yt-dlp":
                # YT-DLP Command
                extra_ytdlp = self.config.get("ytdlp_extra_args", [])
                
                # Format Handling
                fmt = self.config.get("format", "mp3") 
                bitrate = self.config.get("bitrate", "192k") 
                
                # Construct command properly
                cmd = [
                    "yt-dlp",
                    "--ignore-errors", # Skip deleted videos
                    "--extract-audio",
                    "--audio-format", fmt,
                    "--yes-playlist",
                    "--no-progress", # We parse the [download] lines manually
                    "--output", f"{self.output_dir}/%(artist)s - %(title)s.%(ext)s",
                    "--audio-quality", "0", # Best quality (VBR) - User requested to ignore specific bitrate for yt-dlp
                    "--restrict-filenames", # Force ASCII filenames
                    url # <--- CRITICAL: WAS MISSING
                ]
                
                # Check for cookies.txt
                cookies_path = self.config_path.parent / "cookies.txt"
                if cookies_path.exists():
                    cmd.extend(["--cookies", str(cookies_path)])

                cmd.extend(extra_ytdlp)

                cmd.extend(extra_ytdlp)
            
            if not cmd:
                logger.error(f"Herramienta desconocida: {tool}")
                results.append({"url": url, "status": "failed", "attempts": max_att, "error": "Unknown tool"})
                q.task_done()
                continue
            
            # Set state to running for this url
            self.status["state"] = "processing"
            
            while attempts < max_att:
                if self.stop_requested.is_set():
                    logger.info("🛑 Deteniendo bucle principal...")
                    break
                    
                attempts += 1
                msg = f"✨ Procesando: {url} | 🔧 {tool} (Intento {attempts})"
                logger.info(msg)
                if self.broadcast_func: self.broadcast_func("log", msg)
                
                success, logs = self._run_cmd(cmd)
                
                if self.stop_requested.is_set():
                    break

                if success:
                    # Post-process M3U8 to fix paths
                    if m3u_name:
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
                                        
                                    p = Path(line)
                                    filename = p.name
                                    new_lines.append(filename)
                                
                                m3u_file.write_text("\n".join(new_lines), encoding='utf-8')
                                logger.info(f"Corregidas rutas en M3U: {m3u_file}")
                        except Exception as e:
                            logger.error(f"Error procesando M3U: {e}")
                            
                    results.append({"url": url, "status": "success", "attempts": attempts})
                    break # Exit retry loop
                else:
                    logger.warning(f"Error en intento {attempts}.")
                    if attempts < max_att and not self.stop_requested.is_set():
                        time.sleep(retry_cfg.get("backoff_seconds", 5))
                    else:
                        if not self.stop_requested.is_set():
                            logger.error(f"Fallo final para {url}.")
                            results.append({"url": url, "status": "failed", "attempts": attempts})
            
            q.task_done()

    def determine_tool(self, url: str) -> str:
        if "spotify" in url:
            return "spotdl"
        elif "youtube" in url or "youtu.be" in url:
            return "yt-dlp"
        # Fallback heuristic
        if "playlist" in url and "spotify" not in url:
             # Likely youtube playlist ??
             return "yt-dlp"
        return self.config.get("default_tool", "spotdl")

    def process_urls(self, urls: List[str], m3u_name: Optional[str] = None) -> List[Dict]:
        """Procesa una lista de URLs en paralelo.
        
        Args:
            urls: Lista de URLs a descargar
            m3u_name: Nombre opcional para el archivo m3u8 (solo spotdl)
        """
        concurrency = 1
        
        # Ensure directory exists before starting
        if not self.output_dir.exists():
             try:
                 self.output_dir.mkdir(parents=True, exist_ok=True)
                 logger.info(f"📁 Directorio creado: {self.output_dir}")
             except Exception as e:
                 logger.error(f"❌ Error creando directorio {self.output_dir}: {e}")
                 return []
            
        q = queue.Queue()
        results = []
        
        tasks = []
        for u in urls:
            t = self.determine_tool(u)
            tasks.append((u, t, m3u_name))
            
        # Init status
        self.stop_requested.clear() # Reset stop flag
        self.status["state"] = "starting"
        self.status["total_songs"] = 0 # Reset count for new batch
        self.status["downloaded"] = 0
        if self.broadcast_func: self.broadcast_func("status", self.status)
        
        threads = []
        for _ in range(concurrency):
            th = threading.Thread(target=self._download_worker, args=(q, results), daemon=True)
            th.start()
            threads.append(th)
            
        for t in tasks:
            if self.stop_requested.is_set(): break
            q.put(t)
            
        # Wait
        q.join()
        
        # Stop workers gracefully
        for _ in threads:
            q.put(None)
        
        # Join threads with timeout
        for th in threads:
            th.join(timeout=1.0)
        
        # Reset status to idle when done
        self.status["state"] = "idle"
        self.status["current_song"] = None
        if self.broadcast_func: self.broadcast_func("status", self.status)
        
        return results

    def sanitize_files(self) -> Dict[str, int]:
        """
        Renames files in downloads directory to remove:
        1. Youtube IDs in brackets e.g. [dQw4w9WgXcQ]
        2. Emojis and special characters (Preserving Spanish accents)
        3. Updates M3U8 files to match new names
        """
        import re
        import unicodedata
        
        def remove_accents(input_str):
            # Normalize unicode characters to their base form (NFD)
            nfkd_form = unicodedata.normalize('NFKD', input_str)
            # Filter out non-spacing mark characters (accents)
            ascii_str = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
            
            # Manual replacements for edge cases NFD doesn't cover (like Ø)
            replacements = {
                'Ø': 'O', 'ø': 'o',
                'Æ': 'AE', 'æ': 'ae',
                'Œ': 'OE', 'œ': 'oe',
                'ß': 'ss',
                'Ð': 'D', 'ð': 'd',
                'Þ': 'TH', 'þ': 'th',
                'Ł': 'L', 'ł': 'l'
            }
            for char, repl in replacements.items():
                ascii_str = ascii_str.replace(char, repl)
                
            return ascii_str

        renamed_count = 0
        m3u_updated_count = 0
        file_map = {} # old_name -> new_name
        
        # Regex to find brackets at the end of stem: "Song Title [ID].ext"
        bracket_pattern = re.compile(r'\s*\[[^\]]+\]')
        
        msg = "🔪 Iniciando sanitización de archivos (Transliteración)..."
        logger.info(msg)
        if self.broadcast_func: self.broadcast_func("log", msg)
        
        for file in self.output_dir.glob("*"):
            if file.is_dir() or file.suffix == '.m3u8' or file.name.startswith('.'):
                continue
                
            original_name = file.name
            stem = file.stem
            suffix = file.suffix
            
            # 1. Remove brackets (Youtube IDs)
            new_stem = bracket_pattern.sub('', stem)
            
            # 2. Transliterate (Accents -> ASCII) ie: á -> a, ñ -> n
            new_stem = remove_accents(new_stem)

            # 3. Clean Special Chars (Allow only A-Z, 0-9, spaces, and safe punctuation)
            # Now that we are ASCII only, strict filtering is easier
            allowed_chars = " -_.,()'&"
            new_stem = "".join(c for c in new_stem if c.isalnum() or c in allowed_chars).strip()
            
            # 4. Clean up double spaces
            new_stem = re.sub(r'\s+', ' ', new_stem).strip()
            
            # If changed, rename
            new_name = f"{new_stem}{suffix}"
            if new_name != original_name and new_stem:
                try:
                    target = self.output_dir / new_name
                    if not target.exists():
                        file.rename(target)
                        file_map[original_name] = new_name
                        renamed_count += 1
                        logger.info(f"✏️  Renamed: {original_name:<30} -> {new_name}")
                    else:
                        logger.warning(f"⚠️  Target matches, skipping: {new_name}")
                except Exception as e:
                    logger.error(f"❌ Error renaming {original_name}: {e}")

        # 2. Update M3U Files
        if file_map:
            logger.info("📝 Actualizando listas M3U...")
            for m3u in self.output_dir.glob("*.m3u8"):
                try:
                    content = m3u.read_text(encoding='utf-8')
                    lines = content.splitlines()
                    new_lines = []
                    modified = False
                    
                    for line in lines:
                        if line.strip().startswith("#") or not line.strip():
                            new_lines.append(line)
                            continue
                            
                        path = Path(line)
                        fname = path.name
                        
                        if fname in file_map:
                            new_fname = file_map[fname]
                            # Remove leading ./ logic
                            new_lines.append(new_fname)
                            modified = True
                        else:
                            # Also clean existing ./ if present?
                            if line.startswith("./"):
                                new_lines.append(line[2:])
                                modified = True
                            else:
                                new_lines.append(line)
                    
                    if modified:
                        m3u.write_text("\n".join(new_lines), encoding='utf-8')
                        m3u_updated_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ Error updating M3U {m3u.name}: {e}")

        msg = f"✨ Sanitización completada: {renamed_count} archivos renombrados, {m3u_updated_count} listas actualizadas."
        logger.info(msg)
        if self.broadcast_func: self.broadcast_func("log", msg)
        
        return {"renamed": renamed_count, "m3u_updated": m3u_updated_count}
            

