from fastapi import FastAPI, HTTPException, Body, BackgroundTasks
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
import threading
import threading
import os
from pathlib import Path
try:
    from backend.core import DownloaderManager
except ImportError:
    from core import DownloaderManager
import json
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

# Rutas
current_dir = Path(__file__).resolve().parent
if current_dir.name == "app":
    # Docker (usually /app)
    BASE_DIR = current_dir
elif (current_dir / "config.json").exists():
    # Flat structure (e.g. manual run)
    BASE_DIR = current_dir
else:
    # Local (nested structure: script/backend -> script/)
# Local (nested structure: script/backend -> script/)
    BASE_DIR = current_dir.parent

# DEBUG LOGGING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")
logger.info(f"STARTUP DEBUG: current_dir={current_dir}")
logger.info(f"STARTUP DEBUG: current_dir.name={current_dir.name}")
logger.info(f"STARTUP DEBUG: BASE_DIR={BASE_DIR}")
logger.info(f"STARTUP DEBUG: Has SPOTIFY_CLIENT_ID? {bool(os.getenv('SPOTIFY_CLIENT_ID'))}")
logger.info(f"STARTUP DEBUG: Env Keys: {list(os.environ.keys())}")

CONFIG_PATH = BASE_DIR / "config.json"
PLAYLISTS_PATH = BASE_DIR / "playlists.json"
FRONTEND_DIR = BASE_DIR / "frontend"

# Configurar logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

# Servir frontend estático
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Custom Filter to silence /status logs
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("GET /status") == -1

# Filter uvicorn access logs
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

@app.get("/")
async def read_index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/style.css")
async def read_css():
    return FileResponse(FRONTEND_DIR / "style.css")

@app.get("/app.js")
async def read_js():
    return FileResponse(FRONTEND_DIR / "app.js")

if not PLAYLISTS_PATH.exists():
    PLAYLISTS_PATH.write_text("[]", encoding="utf-8")

manager = DownloaderManager(config_path=CONFIG_PATH)

# Models
class ConfigUpdate(BaseModel):
    output_dir: Optional[str] = None
    concurrency: Optional[int] = 2
    format: Optional[str] = "opus"
    spotdl_extra_args: List[str] = None
    ytdlp_extra_args: List[str] = None

class Playlist(BaseModel):
    id: str
    name: str
    urls: List[str]

# Routes
@app.get("/config")
def get_config():
    manager.reload_config()
    config = manager.config.copy()
    config["is_docker"] = (BASE_DIR.name == "app")
    return config

@app.get("/status")
def get_status():
    return manager.status

@app.post("/config")
def update_config(cfg: Dict[str, Any]):
    # Leer config actual
    try:
        current = json.loads(CONFIG_PATH.read_text())
    except:
        current = {}
    
    # Filter out masked secrets to avoid corrupting config.json
    # Removed as we no longer handle credentials
        
    current.update(cfg)
    CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    manager.reload_config()
    manager.verify_dependencies() # Regenerate SpotDL config
    return manager.config

@app.get("/playlists")
def get_playlists():
    try:
        return json.loads(PLAYLISTS_PATH.read_text())
    except:
        return []

@app.post("/playlists")
def save_playlist(playlist: Playlist):
    try:
        data = json.loads(PLAYLISTS_PATH.read_text())
    except:
        data = []
    
    # Upsert logic
    new_data = [p for p in data if p["id"] != playlist.id]
    new_data.append(playlist.model_dump())
    
    PLAYLISTS_PATH.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
    return {"status": "saved"}

@app.delete("/playlists/{id}")
def delete_playlist(id: str):
    try:
        data = json.loads(PLAYLISTS_PATH.read_text())
    except:
        return {"status": "error"}
    
    new_data = [p for p in data if p["id"] != id]
    PLAYLISTS_PATH.write_text(json.dumps(new_data, indent=2), encoding="utf-8")
    return {"status": "deleted"}


scheduler = BackgroundScheduler()
scheduler.start()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

@app.post("/run")
def run_now(background_tasks: BackgroundTasks):
    """Ejecuta todas las playlists configuradas inmediatamente."""
    # Encolar en background para no bloquear
    background_tasks.add_task(execution_job)
    return {"status": "started"}

@app.post("/schedule")
def set_schedule(interval_hours: int = Body(..., embed=True)):
    """Configura la ejecución automática cada X horas."""
    job_id = "auto_download"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    
    if interval_hours > 0:
        scheduler.add_job(execution_job, 'interval', hours=interval_hours, id=job_id)
        return {"status": "scheduled", "interval_hours": interval_hours}
    else:
        return {"status": "disabled"}

def execution_job():
    logger.info("Starting scheduled execution...")
    try:
        if not PLAYLISTS_PATH.exists():
            return

        playlists = json.loads(PLAYLISTS_PATH.read_text())
        total_processed = 0
        
        for p in playlists:
            urls = p.get("urls", [])
            if not urls:
                continue
                
            logger.info(f"Processing playlist: {p['name']}")
            # Process each playlist individually to support Named M3U8s
            manager.process_urls(urls, m3u_name=p["name"])
            total_processed += len(urls)
        
        logger.info(f"Execution finished. Processed {total_processed} URLs.")

    except Exception as e:
        logger.error(f"Execution error: {e}")

@app.get("/playlists/{id}/tracks")
def get_playlist_tracks(id: str):
    try:
        data = json.loads(PLAYLISTS_PATH.read_text())
    except:
        return []

    target_pl = next((p for p in data if p["id"] == id), None)
    if not target_pl:
        raise HTTPException(status_code=404, detail="Playlist not found")

    # Name sanitization must match core.py logic
    m3u_name = target_pl["name"]
    safe_name = "".join(c for c in m3u_name if c.isalnum() or c in (' ', '-', '_')).strip()
    
    # Check current output dir
    manager.reload_config()
    output_dir = Path(manager.config.get("output_dir", "./downloads"))
    
    # In Docker, paths might be sensitive to absolute/relative changes, rely on manager.output_dir
    # However, if manager.output_dir is relative, we need to resolve it relative to wherever we are?
    # Actually manager.output_dir logic in core.py handles it. Here we need to find the file.
    # It is safest to assume absolute path usage or duplicate determination logic.
    # For now, let's use the same logic as core:
    
    m3u_path = output_dir / f"{safe_name}.m3u8"
    
    if not m3u_path.exists():
        return []
        
    tracks = []
    try:
        lines = m3u_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                tracks.append(line)
    except Exception as e:
        logger.error(f"Error reading m3u8: {e}")
        
    return tracks

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
