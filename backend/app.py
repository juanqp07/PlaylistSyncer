
from fastapi import FastAPI, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any
import logging
import threading
from pathlib import Path
from core import DownloaderManager
import uvicorn
import json
from apscheduler.schedulers.background import BackgroundScheduler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

app = FastAPI(title="Downloader Manager API")

BASE_DIR = Path(__file__).parent.parent # /home/juan/Música/script
CONFIG_PATH = BASE_DIR / "config.json"
PLAYLISTS_PATH = BASE_DIR / "playlists.json"

if not PLAYLISTS_PATH.exists():
    PLAYLISTS_PATH.write_text("[]", encoding="utf-8")

manager = DownloaderManager(config_path=CONFIG_PATH)

# Models
class ConfigUpdate(BaseModel):
    output_dir: str = None
    default_tool: str = None
    concurrency: int = None
    retry: Dict[str, int] = None
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
    return manager.config

@app.post("/config")
def update_config(cfg: Dict[str, Any]):
    # Leer config actual
    try:
        current = json.loads(CONFIG_PATH.read_text())
    except:
        current = {}
    
    current.update(cfg)
    CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    manager.reload_config()
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
        all_urls = []
        for p in playlists:
            all_urls.extend(p.get("urls", []))
        
        if all_urls:
            results = manager.process_urls(all_urls)
            logger.info(f"Execution finished. Processed {len(all_urls)} URLs.")
    except Exception as e:
        logger.error(f"Execution error: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
