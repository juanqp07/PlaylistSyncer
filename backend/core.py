
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
    from backend.utils import get_safe_filename, DEFAULT_OUTPUT_DIR
except ImportError:
    from log_parser import LogParser
    from utils import get_safe_filename, DEFAULT_OUTPUT_DIR

# Configurar logger localmente para este módulo
logger = logging.getLogger("downloader.core")



class DownloaderManager:
    def __init__(self, config_path: str, output_dir: Optional[str] = None, broadcast_func: Optional[Callable] = None):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir) if output_dir else None
        self.broadcast_func = broadcast_func
        self.executor = ThreadPoolExecutor(max_workers=1)
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
            raw_path = self.config.get("output_dir", DEFAULT_OUTPUT_DIR)
            # HARD FIX: Detect and fix double-app path caused by relative path misconfiguration in Docker
            s_path = str(raw_path)
            if "/app/app/" in s_path:
                s_path = s_path.replace("/app/app/", "/app/")
                logger.warning(f"⚠️ Detected broken path '{raw_path}', auto-corrected to '{s_path}'")
            self.output_dir = Path(s_path)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verify_dependencies()

    def _kill_by_name(self, target_name: str):
        """
        Safety: Only kills processes belonging to the current user.
        Finds and kills any process containing target_name.
        """
        import pwd
        current_uid = os.getuid()
        
        try:
            # Iterate over all running processes
            for pid_str in os.listdir('/proc'):
                if not pid_str.isdigit():
                    continue
                
                try:
                    pid = int(pid_str)
                    
                    # Verify ownership
                    try:
                        p_info = os.stat(f'/proc/{pid}')
                        if p_info.st_uid != current_uid:
                            continue
                    except:
                        continue
                        
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

    def _get_audio_metadata(self, filename_stub: str) -> tuple[str, int]:
        """
        Resolves full filename (w/ extension) and gets duration.
        Returns (full_filename, duration_seconds).
        """
        # 1. Resolve File
        target_file = None
        # Try exact match first
        p = self.output_dir / filename_stub
        if p.exists():
            target_file = p
        else:
            # Try searching with common extensions
            for ext in [".opus", ".mp3", ".m4a", ".flac", ".ogg"]:
                p = self.output_dir / (filename_stub + ext)
                if p.exists():
                    target_file = p
                    break
        
        if not target_file:
            # Fallback: return original stub and 0 duration (valid-ish)
            return filename_stub, 0
            
        # 2. Get Duration via ffprobe
        duration = 0
        try:
            cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                str(target_file)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                duration = int(float(res.stdout.strip()))
        except:
            pass
            
        return target_file.name, duration

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
                
                # CRITICAL: Sanitize loaded path immediately
                raw_path = self.config.get("output_dir")
                
                # FORCE CORRECT PATH IN DOCKER
                # This overrides any config.json nonsense
                if os.path.exists("/app/.dockerenv") or os.path.exists("/app/app.py") or os.path.exists("/app/backend/app.py"):
                     self.config["output_dir"] = "/app/downloads"
                     self.output_dir = Path("/app/downloads")
                     if raw_path != "/app/downloads":
                         logger.warning(f"🐳 Docker Detected: Forcing output_dir to /app/downloads (Ignored config: {raw_path})")
                else:
                    if raw_path:
                        s_path = str(raw_path)
                        if "/app/app/" in s_path:
                             s_path = s_path.replace("/app/app/", "/app/")
                             self.config["output_dir"] = s_path
                        self.output_dir = Path(self.config["output_dir"])

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

    def _run_cmd(self, cmd: List[str], m3u_path: Optional[str] = None) -> tuple[bool, List[str]]:
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
                    
                     # 3. M3U Generation (Manual for ALL tools)
                     if updates.get("new_filename") and m3u_path:
                         try:
                             # Resolve real filename and duration
                             real_name, duration = self._get_audio_metadata(updates["new_filename"])
                             
                             # Prepare M3U Entry
                             # Logic: If duration > 0, we found the file (with ext), so stem is safe.
                             # If duration == 0, we failed to find file, so real_name might typically be raw name (no ext).
                             # If raw name has dots (e.g. "Feat."), stem would truncate it. Avoid that.
                             if duration > 0:
                                 title = Path(real_name).stem 
                             else:
                                 title = real_name

                             extinf_line = f"#EXTINF:{duration},{title}"
                             file_line = f"./{real_name}"
                             
                             # Read current M3U content
                             current_lines = []
                             has_header = False
                             
                             if os.path.exists(m3u_path):
                                 with open(m3u_path, "r", encoding="utf-8") as f:
                                     raw_lines = f.read().splitlines()
                                     current_lines = [l.strip() for l in raw_lines if l.strip()]
                                     if raw_lines and raw_lines[0].strip() == "#EXTM3U":
                                         has_header = True
                             
                             # Check duplicates (check if filename line exists)
                             if file_line not in current_lines:
                                 with open(m3u_path, "a", encoding="utf-8") as f:
                                     # Add Header if missing/new file
                                     if not has_header and os.path.getsize(m3u_path) == 0:
                                          f.write("#EXTM3U\n")
                                     elif not has_header and not os.path.exists(m3u_path): # Should be covered by size check but safe
                                          f.write("#EXTM3U\n")

                                     # Defensive newline if needed (not empty file)
                                     if os.path.exists(m3u_path) and os.path.getsize(m3u_path) > 0:
                                         # Check last char? simplified: just Ensure usage of new lines
                                         f.write("\n")
                                     
                                     f.write(f"{extinf_line}\n{file_line}")
                                     
                                 logger.info(f"📝 Added to M3U: {real_name}")
                             else:
                                 logger.info(f"⏭ En M3U (Skipping add): {real_name}")
                                 
                         except Exception as e:
                             logger.error(f"Failed to append to M3U: {e}")

                     # 4. FRONTEND BROADCAST (Pretty/Modified)
                     if updates:
                         if "downloaded_increment" in updates:
                             self.status["downloaded"] += updates.pop("downloaded_increment")
                             
                         if "log_message" in updates:
                             if self.broadcast_func:
                                 # Send raw message with ANSI codes so frontend can parse colors
                                 self.broadcast_func("log", updates["log_message"])
                         
                         for k, v in updates.items():
                             if k not in ["log_message", "log_level", "log_raw", "new_filename"]:
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
            m3u_arg = None
            
            # CRITICAL: Playlist Isolation
            # Ensure output_dir is absolute and exists
            self.output_dir = self.output_dir.resolve()
            
            # HARD FIX: Double check for double /app/app which shouldn't happen with new logic but just in case
            s_out = str(self.output_dir)
            if "/app/app/" in s_out:
                new_out = s_out.replace("/app/app/", "/app/")
                logger.warning(f"⚠️ Caught runtime double-app path: {s_out} -> {new_out}")
                self.output_dir = Path(new_out)
            try:
                if not self.output_dir.exists():
                     self.output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to ensure root output dir {self.output_dir}: {e}")

            target_dir = self.output_dir
            if m3u_name:
                # Sanitize using centralized logic
                safe_pl_name = get_safe_filename(m3u_name)
                    
                target_dir = self.output_dir / safe_pl_name
                
                # ROBUST MKDIR
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.error(f"Error creating dir {target_dir}: {e}")

                m3u_arg = f"{target_dir}/{safe_pl_name}.m3u8"
                
                # CRITICAL FIX: Ensure the PARENT directory of the M3U file exists before SpotDL tries to write to it
                # This handles cases where SpotDL resolves paths weirdly or target_dir failed silently
                try:
                    Path(m3u_arg).parent.mkdir(parents=True, exist_ok=True)
                except:
                    pass
            else:
                 # Single song or untracked -> root downloads
                 target_dir = self.output_dir
                 if m3u_name: 
                     pass

            if tool == "spotdl":
                # Construir comando (SpotDL)
                import hashlib
                # Sync dir inside the target folder to keep it self-contained
                sync_dir = target_dir / ".sync"
                
                if not sync_dir.exists():
                    try:
                        sync_dir.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo crear directorio .sync: {e}")
                
                # If url is a search query (no protocol), hash might be ugly, but functional
                if isinstance(url, list):
                     # For batch, hash the first item + count to be unique enough
                     url_hash = hashlib.md5((url[0] + str(len(url))).encode("utf-8")).hexdigest()
                else: 
                     url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
                     
                save_file = sync_dir / f"{url_hash}.spotdl"
                
                # Obtener formato y bitrate
                fmt = self.config.get("format", "opus")
                bitrate = self.config.get("bitrate", "192k")
                
                # Determine Mode: URL vs Search Query
                # Hybrid M3U Logic
                # If URL (Spotify Playlist/Track): Use SpotDL native --m3u (User prefers this)
                # If Title (YouTube Extraction): Use Manual Append (SpotDL overwrite fix)
                # Hybrid M3U Logic
                run_cmd_m3u_arg = None 
                
                # Input Handling (Batch vs Single)
                inputs = []
                is_batch = isinstance(url, list)
                if is_batch:
                    inputs = url
                    # For batches (TITLES), we are definitely in Manual Mode
                    # No sync file, No native M3U
                    run_cmd_m3u_arg = m3u_arg
                    # Use first title for display/hash if needed, or just "Batch" in logging
                else:
                    inputs = [url]
                
                # Determine Mode (URL vs Title)
                # If ANY input starts with http, treat as URL mode (likely single)
                # If batch, assume Titles (Manual)
                is_url_mode = any(u.startswith("http") for u in inputs)
                
                # Base Command
                cmd.extend(["spotdl", "download"])
                cmd.extend(inputs) # Add all titles/urls
                
                cmd.extend([
                    "--output", f"{target_dir}/{{artist}} - {{title}}",
                    "--format", fmt,
                    "--bitrate", bitrate,
                    "--restrict", "ascii", # Force ASCII filenames
                    "--threads", "1", # CRITICAL: Force sequential processing to avoid FFmpeg/Resource errors
                ])

                if is_url_mode and not is_batch:
                    # Native Mode (Single Spotify Playlist/URL)
                    cmd.extend(["--save-file", str(save_file)])
                    cmd.extend(["--m3u", m3u_arg])
                else:
                    # Manual Mode (Titles or Batch)
                    run_cmd_m3u_arg = m3u_arg

                
                # Check for cookies.txt
                cookies_path = self.config_path.parent / "cookies.txt"
                if cookies_path.exists():
                    cmd.extend(["--cookie-file", str(cookies_path)])
                    
                cmd.extend(extra_args)


            else:
                 # Fallback (Should not happen with current logic, but keeps safety)
                 logger.error(f"Herramienta no soportada o eliminada: {tool}")
                 q.task_done()
                 continue
            
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
                if isinstance(url, list):
                     msg = f"✨ Procesando lote de {len(url)} canciones | 🔧 {tool} (Intento {attempts})"
                else:
                     msg = f"✨ Procesando: {url} | 🔧 {tool} (Intento {attempts})"
                
                logger.info(msg)
                if self.broadcast_func: self.broadcast_func("log", msg)
                
                # Pass run_cmd_m3u_arg to trigger manual append only if needed
                success, logs = self._run_cmd(cmd, run_cmd_m3u_arg)
                
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
                                    # Enforce ./ prefix to match _run_cmd logic and user preference
                                    if not filename.startswith("./"):
                                        filename = f"./{filename}"
                                    new_lines.append(filename)
                                
                                # Ensure trailing newline
                                m3u_file.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
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
        concurrency = 1 # Force concurrency to 1 as requested to avoid rate limits

        
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
        tasks = []
        
        # Initial Log for Playlist start (if m3u_name provided)
        if m3u_name:
             msg = f"📀 Procesando Playlist: {m3u_name}"
             logger.info(msg)
             if self.broadcast_func: self.broadcast_func("log", msg)

        for u in urls:
            # Check if YouTube URL
            if "youtube" in u or "youtu.be" in u:
                msg = f"🔎 Analizando Playlist de YouTube: {u}..."
                logger.info(msg)
                if self.broadcast_func: self.broadcast_func("log", msg)
                
                try:
                    # Run yt-dlp to get titles (flat-playlist)
                    # --print "%(title)s" gives us just the title per line
                    cmd = ["yt-dlp", "--flat-playlist", "--print", "%(title)s", u]
                    
                    # Check for cookies
                    cookies_path = self.config_path.parent / "cookies.txt"
                    if cookies_path.exists():
                        cmd.extend(["--cookies", str(cookies_path)])
                        
                    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
                    if res.returncode == 0:
                        titles = res.stdout.strip().splitlines()
                        
                        msg = f"✅ Títulos extraídos de YouTube: {len(titles)} canciones encontradas."
                        logger.info(msg)
                        if self.broadcast_func: self.broadcast_func("log", msg)

                        # Optimization: Batch titles to avoid 66x python startup overhead
                        # Batch size 50 is safe for command line length
                        batch_size = 50
                        current_batch = []
                        
                        # Pre-compile regex for cleaning titles
                        import re
                        # Patterns to remove: text inside parens/brackets containing "video", "oficial", "official", "lyric"
                        # Also explicit "ft." junk if needed, but usually minimal is better.
                        # Case insensitive.
                        clean_pattern = re.compile(r'\s*[\(\[](?:[^)\].]*?(?:video|official|oficial|lyric|letra)[^)\].]*?)[\)\]]', re.IGNORECASE)

                        for title in titles:
                            if title.strip():
                                # CLEAN TITLE
                                clean_title = clean_pattern.sub('', title)
                                # Clean up extra spaces
                                clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                                
                                if clean_title:
                                    current_batch.append(clean_title)
                                    if len(current_batch) >= batch_size:
                                        tasks.append((current_batch, "spotdl", m3u_name))
                                        current_batch = []
                        
                        # Add remaining
                        if current_batch:
                            tasks.append((current_batch, "spotdl", m3u_name))
                            
                    else:
                         logger.error(f"❌ Error extrayendo playlist de YT: {res.stderr}")
                         # Fallback: try adding url directly? No, user doesn't want yt-dlp download
                         results.append({"url": u, "status": "failed", "error": "YT extract failed"})

                except Exception as e:
                    logger.error(f"❌ Excepción extrayendo YT: {e}")
                    results.append({"url": u, "status": "failed", "error": str(e)})
            else:
                 # Standard SpotDL (Spotify URL)
                 tasks.append((u, "spotdl", m3u_name))
            
        # Init status
        self.stop_requested.clear() # Reset stop flag
        self.status["state"] = "starting"
        
        # Calculate strict total songs (accounting for batches)
        total_count = 0
        for t in tasks:
            # t is (url_or_list, tool, m3u_name)
            input_data = t[0]
            if isinstance(input_data, list):
                total_count += len(input_data)
            else:
                total_count += 1
                
        self.status["total_songs"] = total_count
        self.status["downloaded"] = 0
        
        msg = f"🚀 Iniciando descarga de {total_count} canciones..."
        logger.info(msg)
        if self.broadcast_func:
             self.broadcast_func("log", msg)
             self.broadcast_func("status", self.status)

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
        Renames files in downloads directory AND subdirectories to remove:
        1. Youtube IDs in brackets e.g. [dQw4w9WgXcQ]
        2. Emojis and special characters (Preserving Spanish accents)
        3. Updates M3U8 files to match new names
        """
        import re
    def sanitize_files(self) -> Dict[str, int]:
        """
        Renames files in downloads directory AND subdirectories to remove:
        1. Youtube IDs in brackets e.g. [dQw4w9WgXcQ]
        2. Emojis and special characters (Preserving Spanish accents)
        3. Updates M3U8 files to match new names
        """
        import re
        
        renamed_count = 0
        m3u_updated_count = 0
        
        # Regex to find brackets at the end of stem: "Song Title [ID].ext"
        bracket_pattern = re.compile(r'\s*\[[^\]]+\]')
        
        msg = "🔪 Iniciando sanitización recursiva de archivos..."
        logger.info(msg)
        if self.broadcast_func: self.broadcast_func("log", msg)
        
        # Helper function to process a single directory
        def process_directory(directory: Path):
            nonlocal renamed_count, m3u_updated_count
            file_map = {} # old_name -> new_name within this dir
            
            # 1. Rename Files
            for file in directory.glob("*"):
                if file.is_dir() or file.suffix == '.m3u8' or file.name.startswith('.'):
                    continue
                    
                original_name = file.name
                stem = file.stem
                suffix = file.suffix
                
                # 1. Remove brackets (Youtube IDs)
                new_stem = bracket_pattern.sub('', stem)
                
                # 2. Use Centralized Sanitization (Handles accents, special chars, double spaces)
                new_stem = get_safe_filename(new_stem)
                
                # If changed, rename
                new_name = f"{new_stem}{suffix}"
                if new_name != original_name and new_stem:
                    try:
                        target = directory / new_name
                        if not target.exists():
                            file.rename(target)
                            file_map[original_name] = new_name
                            renamed_count += 1
                            logger.info(f"✏️  Renamed: {original_name:<30} -> {new_name}")
                        else:
                            logger.warning(f"⚠️  Target matches, skipping: {new_name}")
                    except Exception as e:
                        logger.error(f"❌ Error renaming {original_name}: {e}")

            # 2. Update M3U Files in this directory
            if file_map:
                logger.info(f"📝 Actualizando listas M3U en {directory.name}...")
                for m3u in directory.glob("*.m3u8"):
                    try:
                        content = m3u.read_text(encoding='utf-8')
                        lines = content.splitlines()
                        new_lines = []
                        modified = False
                        
                        for line in lines:
                            if line.strip().startswith("#") or not line.strip():
                                new_lines.append(line)
                                continue
                                
                            # Handle paths like ./Start - Title.mp3
                            original_clean = line.strip()
                            prefix = ""
                            if original_clean.startswith("./"):
                                prefix = "./"
                                original_clean = original_clean[2:]
                            
                            path = Path(original_clean)
                            fname = path.name
                            
                            if fname in file_map:
                                new_fname = file_map[fname]
                                new_lines.append(prefix + new_fname)
                                modified = True
                            else:
                                new_lines.append(line)
                        
                        if modified:
                            m3u.write_text("\n".join(new_lines) + "\n", encoding='utf-8')
                            m3u_updated_count += 1
                            
                    except Exception as e:
                        logger.error(f"❌ Error updating M3U {m3u.name}: {e}")
        
        # 1. Process Root Directory
        process_directory(self.output_dir)
        
        # 2. Process Subdirectories (Playlist Folders)
        try:
            for item in self.output_dir.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    process_directory(item)
        except Exception as e:
            logger.error(f"Error traversing directories: {e}")

        msg = f"✨ Sanitización completada: {renamed_count} archivos renombrados."
        logger.info(msg)
        if self.broadcast_func: self.broadcast_func("log", msg)
        
        return {"renamed": renamed_count, "m3u_updated": m3u_updated_count}
