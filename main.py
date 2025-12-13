#!/usr/bin/env python3
"""
Wrapper Python para spotdl y yt-dlp inspirado en tu main.sh.
Características:
- Lee config.json para opciones (formato, bitrate, output, args extra).
- Soporta descargar URLs individuales, listas desde archivo y playlists.
- Invoca spotdl o yt-dlp según configuración o por opción.
- Maneja reintentos básicos y logging.

Nota: Este script es un punto de partida. spotdl y yt-dlp tienen muchas opciones
y aquí se pasan args extra desde config.json para mantener flexibilidad.
"""
import argparse
import json
import logging
import shutil
import subprocess
import sys
import threading
import queue
import time
from pathlib import Path

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("download.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

def load_config():
    if not CONFIG_PATH.exists():
        logger.error(f"No se encontró {CONFIG_PATH}. Copia config.example.json a config.json y edita.")
        sys.exit(1)
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error(f"Error al leer config.json: {e}")
        sys.exit(1)

cfg = load_config()

def verify_dependencies():
    """Verifica que las herramientas necesarias estén instaladas."""
    missing = []
    for tool in ["spotdl", "yt-dlp"]:
        if not shutil.which(tool):
            missing.append(tool)
    
    if missing:
        logger.error(f"Faltan herramientas requeridas: {', '.join(missing)}")
        logger.info("Por favor instálalas (pip install spotdl yt-dlp) y asegúrate de que estén en el PATH.")
        sys.exit(1)

def run_cmd(cmd, check=True):
    """Ejecuta el comando en shell y loguea la salida."""
    cmd_str = ' '.join(cmd)
    logger.debug(f"[CMD] {cmd_str}")
    
    # Usamos subprocess.PIPE para capturar, pero en un entorno real a veces queremos ver el progreso
    # yt-dlp y spotdl escriben mucho a stdout/stderr.
    # Para simplicidad y logging, capturamos y logueamos si hay error,
    # o imprimimos en debug si todo va bien (para no saturar).
    
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output_lines = []
    
    try:
        for line in proc.stdout:
            line = line.rstrip()
            output_lines.append(line)
            # Opcional: imprimir progreso real si se desea, 
            # pero con hilos concurrentes se mezclará la salida.
            # logger.debug(f"OUTPUT: {line}") 
    except Exception as e:
        proc.kill()
        logger.error(f"Excepción ejecutando {cmd[0]}: {e}")
        raise

    proc.wait()
    
    if check and proc.returncode != 0:
        # En caso de error, volcar las últimas líneas de salida al log
        logger.error(f"Comando falló: {cmd_str}")
        for l in output_lines[-10:]: # Últimas 10 líneas
            logger.error(f"  > {l}")
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    
    return proc.returncode

def download_item(tool, url, output_dir, extra_args):
    if tool == "spotdl":
        cmd = ["spotdl", url, "--output", str(output_dir)]
        cmd += extra_args
    else:
        # yt-dlp
        cmd = ["yt-dlp", url, "-P", str(output_dir)]
        cmd += extra_args
    return run_cmd(cmd)

def worker(q, results, output_dir, spotdl_args, ytdlp_args, retry_cfg):
    while True:
        item = q.get()
        if item is None:
            break
        
        url, idx, tool = item
        attempts = 0
        success = False
        
        max_attempts = retry_cfg.get("attempts", 1)
        
        while attempts < max_attempts and not success:
            attempts += 1
            logger.info(f"[{idx}] Iniciando descarga con {tool} (intento {attempts}/{max_attempts}): {url}")
            
            try:
                extra_args = spotdl_args if tool == "spotdl" else ytdlp_args
                download_item(tool, url, output_dir, extra_args)
                
                success = True
                logger.info(f"[{idx}] Éxito: {url}")
                results.append((url, True, attempts))
                
            except subprocess.CalledProcessError:
                logger.warning(f"[{idx}] Fallo en intento {attempts} para {url}")
                if attempts < max_attempts:
                    backoff = retry_cfg.get("backoff_seconds", 5)
                    logger.info(f"[{idx}] Reintentando en {backoff}s...")
                    time.sleep(backoff)
                else:
                    logger.error(f"[{idx}] Fallo definitivo para {url}")
                    results.append((url, False, attempts))
            except Exception as e:
                logger.error(f"[{idx}] Error inesperado para {url}: {e}")
                results.append((url, False, attempts))
                break # No reintentar errores inesperados (bugs, etc)

        q.task_done()

def gather_urls_from_file(path):
    urls = []
    if not os.path.exists(path):
        logger.error(f"No se encontró el archivo de lista: {path}")
        return []
        
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls

def is_playlist_or_spotify(url):
    return ("playlist" in url) or ("spotify" in url and "track" not in url)

def determine_tool(url, force_tool, default_tool):
    if force_tool:
        return force_tool
    
    # Detección simple
    if "spotify" in url:
        return "spotdl"
    elif "youtube" in url or "youtu.be" in url:
        return "yt-dlp"
    
    # Fallback heurístico anterior
    if is_playlist_or_spotify(url):
        return "spotdl"
    
    return default_tool

def main():
    parser = argparse.ArgumentParser(description="Wrapper para spotdl/yt-dlp con config.json")
    parser.add_argument("urls", nargs="*", help="URLs a descargar")
    parser.add_argument("-f", "--file", help="Archivo con URLs (una por línea)")
    parser.add_argument("-o", "--output", help="Directorio de salida (sobrescribe config)")
    parser.add_argument("--tool", choices=["spotdl","ytdlp"], help="Forzar herramienta a usar")
    parser.add_argument("--concurrency", type=int, help="Número de descargas concurrentes (sobrescribe config)")
    args = parser.parse_args()

    verify_dependencies()

    config = cfg

    output_dir = Path(args.output) if args.output else Path(config.get("output_dir", "./downloads"))
    output_dir.mkdir(parents=True, exist_ok=True)

    extra_spotdl = config.get("spotdl_extra_args", [])
    extra_ytdlp = config.get("ytdlp_extra_args", [])

    # Construir lista de URLs
    urls = list(args.urls)
    if args.file:
        urls += gather_urls_from_file(args.file)

    if not urls:
        logger.warning("No se proporcionaron URLs. Usa --file o pasa URLs como argumentos.")
        # No salimos con error, solo terminamos limpiamente
        return

    # Preparar tareas
    tasks = []
    default_tool = config.get("default_tool", "spotdl")
    
    for u in urls:
        chosen_tool = determine_tool(u, args.tool, default_tool)
        tasks.append((u, chosen_tool))

    concurrency = args.concurrency if args.concurrency is not None else config.get("concurrency", 2)
    q = queue.Queue()
    results = []

    # Encolar: (url, index, tool)
    # IMPORTANTE: Ahora pasamos la tool elegida a la cola
    for idx, (u, t) in enumerate(tasks, start=1):
        q.put((u, idx, t))

    logger.info(f"Iniciando {len(tasks)} descargas con concurrencia {concurrency}...")

    threads = []
    retry_cfg = config.get("retry", {"attempts": 1, "backoff_seconds": 5})
    
    for i in range(concurrency):
        # El worker ya no recibe 'tool' fijo, lo saca de la cola
        t = threading.Thread(
            target=worker, 
            args=(q, results, output_dir, extra_spotdl, extra_ytdlp, retry_cfg), 
            daemon=True
        )
        t.start()
        threads.append(t)

    q.join()
    
    for _ in threads:
        q.put(None)
    for t in threads:
        t.join(timeout=1)

    # Resumen
    success_count = sum(1 for r in results if r[1])
    failed_items = [r for r in results if not r[1]]
    
    logger.info(f"Resumen final: {success_count} completados, {len(failed_items)} fallidos.")
    
    if failed_items:
        logger.error("Lista de fallos:")
        for url, ok, attempts in failed_items:
            logger.error(f"- {url} (intentos: {attempts})")
        sys.exit(1)

if __name__ == "__main__":
    main()
