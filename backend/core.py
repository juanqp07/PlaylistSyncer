
import json
import logging
import shutil
import subprocess
import threading
import queue
import time
import os
from pathlib import Path

# Configurar logger localmente para este módulo
logger = logging.getLogger("downloader.core")

class DownloaderManager:
    def __init__(self, config_path, output_dir=None):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir) if output_dir else None
        self.config = {}
        self.reload_config()
        
        # Si no se pasó output_dir en init, usar el del config
        if not self.output_dir:
            self.output_dir = Path(self.config.get("output_dir", "./downloads"))
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verify_dependencies()

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
        
        # Crear config de SpotDL
        try:
            # Prioritize Env Vars
            client_id = os.getenv("SPOTIFY_CLIENT_ID") or self.config.get("spotify_client_id", "")
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET") or self.config.get("spotify_client_secret", "")
            lyrics_provider = self.config.get("lyrics_provider", "genius")
            
            conf_data = {
                "lyrics_providers": [lyrics_provider],
                "client_id": client_id,
                "client_secret": client_secret
            }
            
            # If user hasn't configured them, maybe don't write them? 
            # SpotDL might error if empty strings are passed.
            if not client_id or not client_secret:
                conf_data.pop("client_id", None)
                conf_data.pop("client_secret", None)

            # Write config to the standard location (SpotDL 4.x+)
            # Based on 'spotdl --generate-config' output, this is the authoritative path.
            config_path = Path.home() / ".config" / "spotdl" / "config.json"
            
            try:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                json_str = json.dumps(conf_data, indent=2)
                config_path.write_text(json_str, encoding="utf-8")
                logger.info(f"SpotDL config escrito en: {config_path}")
                logger.info(f"Contenido config SpotDL: {json_str}")
            except Exception as e:
                logger.warning(f"No se pudo escribir config en {config_path}: {e}")
                    
        except Exception as e:
            logger.warning(f"Error general creando config de SpotDL: {e}")

    def _run_cmd(self, cmd):
        cmd_str = ' '.join(cmd)
        logger.debug(f"[CMD] {cmd_str}")
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out_lines = []
        try:
            for line in proc.stdout:
                line = line.strip()
                if line:
                    out_lines.append(line)
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
                
                # Obtener formato y bitrate
                fmt = self.config.get("format", "mp3")
                bitrate = self.config.get("bitrate", "320k")
                
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
                    "--m3u", m3u_arg,
                    "--lyrics", lyrics_provider,
                    "--no-cache"
                ]
                
                # Explicitly pass credentials if available to avoid 429 errors
                client_id = os.getenv("SPOTIFY_CLIENT_ID") or self.config.get("spotify_client_id", "")
                client_secret = os.getenv("SPOTIFY_CLIENT_SECRET") or self.config.get("spotify_client_secret", "")
                
                if client_id and client_secret and client_id != "********":
                    cmd.extend(["--client-id", client_id, "--client-secret", client_secret])
            else:
                cmd = ["yt-dlp", url, "-P", str(self.output_dir)]
            
            cmd += extra_args

            while attempts < max_att and not success:
                attempts += 1
                logger.info(f"Descargando {url} con {tool} (Intento {attempts})")
                
                ok, lines = self._run_cmd(cmd)
                if ok:
                    success = True
                    results.append({"url": url, "status": "success", "attempts": attempts})
                else:
                    logger.warning(f"Error en intento {attempts}. Salida:\n" + "\n".join(lines[-10:]))
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
            
        return results
