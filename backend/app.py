from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, WebSocket, WebSocketDisconnect
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import logging
import threading
import asyncio
import os
from pathlib import Path
try:
    from backend.core import DownloaderManager
except ImportError:
    from core import DownloaderManager

# Database Module import
try:
    import backend.database as db
    from backend.utils import get_safe_filename, DEFAULT_OUTPUT_DIR
except ImportError:
    import database as db
    from utils import get_safe_filename, DEFAULT_OUTPUT_DIR

import json
from apscheduler.schedulers.background import BackgroundScheduler

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass
                
connection_manager = ConnectionManager()

app = FastAPI()

# Rutas
# Rutas
current_dir = Path(__file__).resolve().parent
# Simple Docker Detection via Env/File
if os.getenv("IS_DOCKER") or (current_dir.name == "app"):
    BASE_DIR = current_dir
else:
    # Check if we are in backend/ subdir (Local dev)
    if current_dir.name == "backend":
         BASE_DIR = current_dir.parent
    else:
         BASE_DIR = current_dir

# Logger config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

CONFIG_PATH = BASE_DIR / "config.json"
PLAYLISTS_PATH = BASE_DIR / "playlists.json"
FRONTEND_DIR = BASE_DIR / "frontend"

# Servir frontend estático
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Mount /js for modular scripts
js_dir = FRONTEND_DIR / "js"
app.mount("/js", StaticFiles(directory=js_dir), name="js")


# Custom Filter to silence /status logs
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("GET /status") == -1

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

# Helper to bridge Sync (Core) -> Async (WebSockets)
def broadcast_to_ws(event_type: str, data: Any):
    pass

main_loop = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    # Initialize DB
    db.init_db()
    
    # Restore Schedule from Config
    manager.reload_config()
    interval = manager.config.get("schedule_interval_hours", 0)
    if interval > 0:
        logger.info(f"Restoring schedule: Every {interval} hours")
        scheduler.add_job(execution_job, 'interval', hours=interval, id="auto_download")
    
    # Run Migration
    run_migration_if_needed()

def run_migration_if_needed():
    """Migrates JSON playlists to SQLite if they exist."""
    if not PLAYLISTS_PATH.exists():
        return
        
    try:
        content = PLAYLISTS_PATH.read_text(encoding="utf-8")
        if not content.strip():
            return
            
        old_data = json.loads(content)
        if not isinstance(old_data, list) or not old_data:
            return

        count = 0
        for pl in old_data:
            if not db.get_playlist(pl["id"]):
                db.save_playlist(pl["id"], pl["name"], pl["urls"], pl.get("track_count", 0))
                count += 1
        
        if count > 0:
            logger.info(f"Migrated {count} playlists from JSON to SQLite.")
            PLAYLISTS_PATH.write_text("[]", encoding="utf-8")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")

@app.post("/schedule")
def set_schedule(interval_hours: int = Body(..., embed=True)):
    """Configura la ejecución automática cada X horas y persiste la configuración."""
    job_id = "auto_download"
    
    # 1. Save to Config
    try:
        current = json.loads(CONFIG_PATH.read_text())
    except:
        current = {}
    
    current["schedule_interval_hours"] = interval_hours
    CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    manager.reload_config()

    # 2. Update Scheduler
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    
    if interval_hours > 0:
        scheduler.add_job(execution_job, 'interval', hours=interval_hours, id=job_id)
        return {"status": "scheduled", "interval_hours": interval_hours}
    else:
        return {"status": "disabled"}
def sync_broadcast(event_type, data):
    msg = {"type": event_type, "data": data}
    if main_loop and connection_manager.active_connections:
        asyncio.run_coroutine_threadsafe(connection_manager.broadcast(msg), main_loop)

manager = DownloaderManager(config_path=str(CONFIG_PATH), broadcast_func=sync_broadcast)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await connection_manager.connect(websocket)
    # Send current status immediately
    await websocket.send_json({"type": "status", "data": manager.status})
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)

# Models
class ConfigUpdate(BaseModel):
    output_dir: Optional[str] = None
    format: Optional[str] = "opus"
    bitrate: Optional[str] = "192k"
    spotdl_extra_args: List[str] = None
    ytdlp_extra_args: List[str] = None

class SettingsUpdate(BaseModel):
    output_dir: Optional[str] = None
    concurrency: Optional[int] = None

class Playlist(BaseModel):
    id: str
    name: str
    urls: List[HttpUrl]

# Routes
@app.get("/config")
def get_config():
    manager.reload_config()
    config = manager.config.copy()
    config["is_docker"] = (BASE_DIR.name == "app")
    config["version"] = "1.7.6" 
    return config

@app.get("/status")
def get_status():
    return manager.status

@app.post("/settings")
def update_settings(settings: SettingsUpdate):
    try:
        current = manager.config.copy()
        
        # Merge
        if settings.output_dir is not None:
             # Sanitize incoming path too
             path = settings.output_dir
             if "/app/app/" in path:
                 path = path.replace("/app/app/", "/app/")
             current["output_dir"] = path
             
        if settings.concurrency is not None: current["concurrency"] = settings.concurrency
        CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")
    manager.reload_config()
    manager.verify_dependencies() 
    return manager.config

@app.get("/playlists")
def get_playlists():
    return db.get_playlists()

@app.post("/playlists")
def save_playlist(playlist: Playlist):
    try:
        # Convert HttpUrl objects to strings for storage
        urls_str = [str(u) for u in playlist.urls]
        db.save_playlist(playlist.id, playlist.name, urls_str)
        return {"status": "saved"}
    except Exception as e:
        logger.error(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.delete("/playlists/{id}")
def delete_playlist(id: str):
    pl = db.get_playlist(id)
    if pl:
        # Delete from DB
        db.delete_playlist(id)
        
        # Try to delete folder
        try:
           manager.reload_config()
           output_dir = Path(manager.config.get("output_dir", DEFAULT_OUTPUT_DIR))
           
           safe_name = get_safe_filename(pl["name"])
           target_dir = output_dir / safe_name
           
           import shutil
           if target_dir.exists() and target_dir.is_dir():
               shutil.rmtree(target_dir)
               logger.info(f"Deleted folder: {target_dir}")
        except Exception as e:
            logger.error(f"Failed to delete folder for {pl['name']}: {e}")
            
    return {"status": "deleted"}

@app.post("/playlists/{id}/sync")
def sync_playlist_now(id: str, background_tasks: BackgroundTasks):
    pl = db.get_playlist(id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    background_tasks.add_task(execution_job_single, pl)
    return {"status": "started", "playlist": pl["name"]}

@app.get("/history")
def get_history():
    return db.get_history()

scheduler = BackgroundScheduler()
scheduler.start()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

@app.post("/run")
def run_now(background_tasks: BackgroundTasks):
    """Ejecuta todas las playlists configuradas inmediatamente."""
    background_tasks.add_task(execution_job)
    return {"status": "started"}

@app.post("/stop")
def stop_job():
    """Detiene la descarga en curso."""
    manager.stop()
    return {"status": "stopping"}

@app.post("/api/retry/{id}")
async def retry_download(id: str):
    # Logic to restart a specific download (not fully implemented in core yet)
    # For now, we can just return ok
    return {"status": "queued"}

@app.post("/api/sanitize")
async def sanitize_files():
    """Renombra archivos eliminando IDs y emojis para compatibilidad."""
    stats = manager.sanitize_files()
    return {"status": "ok", "stats": stats}

def migrate_db():
    pass # Ya manejado en startup

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

def execution_job_single(p: Dict):
    """Ejecuta una sola playlist (Background Task)"""
    import time
    start_time = time.time()
    
    logger.info(f"Manual Sync: {p['name']}")
    
    # Check urls
    urls = p.get("urls", [])
    if not urls:
        return

    manager.update_status("playlist_name", p['name'])
    
    # Process
    results = manager.process_urls(urls, m3u_name=p["name"])
    
    # Calculate stats
    duration = time.time() - start_time
    downloaded = sum(1 for r in results if r.get("status") == "success") # This is rough, as Core tracks downloaded count globally for the session
    # Better to ask manager status but status resets.
    # Results is List of dicts. If manager modifies it we can check?
    # Manager returns list of results: {url, status, attempts}
    
    db.add_history_entry(
        playlist_name=p["name"],
        status="completed",
        downloaded=downloaded,
        total=len(urls),
        duration=duration
    )
    
    # Update Track Count
    update_track_count_for_playlist(p)

def execution_job():
    logger.info("Starting scheduled execution...")
    import time
    start_time = time.time()
    total_processed = 0
    downloaded_count = 0
    
    try:
        # Use DB
        playlists = db.get_playlists()
        if not playlists:
            logger.info("No playlists to schedule.")
            return

        for p in playlists:
            urls = p.get("urls", [])
            if not urls:
                continue
                
            logger.info(f"Processing playlist: {p['name']}")
            
            manager.update_status("playlist_name", p['name'])
            
            # Process
            try:
                results = manager.process_urls(urls, m3u_name=p["name"])
                total_processed += len(urls)
                # Count successes in this batch
                downloaded_count += sum(1 for r in results if r.get("status") == "success")
            except Exception as e:
                logger.error(f"Error processing playlist {p['name']}: {e}")
            
            # CRITICAL: Check if stop was requested during processing
            if manager.stop_requested.is_set():
                logger.info("Stop requested. Aborting remaining playlists.")
                break
            
        # Update Track Counts
        playlists_latest = db.get_playlists()
        for p in playlists_latest:
           update_track_count_for_playlist(p)

    except Exception as e:
        logger.error(f"Execution fatal error: {e}")
    finally:
        # Always log to history if we did something
        duration = time.time() - start_time
        
        # Don't log if zero items processed (unless it was an error? But we want to avoid spam if empty)
        if total_processed > 0 or duration > 5:
            try:
                db.add_history_entry(
                    playlist_name="Scheduled Sync",
                    status="completed",
                    downloaded=downloaded_count,
                    total=total_processed,
                    duration=duration
                )
                logger.info(f"Scheduled execution finished. Processed {total_processed} URLs.")
            except Exception as h_err:
                logger.error(f"Failed to save history: {h_err}")

def update_track_count_for_playlist(p):
    manager.reload_config()
    output_dir = Path(manager.config.get("output_dir", DEFAULT_OUTPUT_DIR))
    
    m3u_name = p["name"]
    safe_name = get_safe_filename(m3u_name)
    
    # Check in subfolder first (New Structure)
    m3u_path = output_dir / safe_name / f"{safe_name}.m3u8"
    if not m3u_path.exists():
        # Fallback to old root structure
        m3u_path = output_dir / f"{safe_name}.m3u8"
    
    count = 0
    if m3u_path.exists():
        try:
            lines = m3u_path.read_text(encoding="utf-8").splitlines()
            count = sum(1 for line in lines if line.strip() and not line.startswith("#"))
        except:
            pass
    
    if p.get("track_count") != count:
        db.update_track_count(p["id"], count)
        logger.info(f"Updated track count for {p['name']}: {count}")

@app.get("/playlists/{id}/tracks")
def get_playlist_tracks(id: str):
    target_pl = db.get_playlist(id)
    if not target_pl:
        raise HTTPException(status_code=404, detail="Playlist not found")

    m3u_name = target_pl["name"]
    safe_name = get_safe_filename(m3u_name)
    
    manager.reload_config()
    output_dir = Path(manager.config.get("output_dir", DEFAULT_OUTPUT_DIR))
    
    # Check in subfolder first (New Structure)
    m3u_path = output_dir / safe_name / f"{safe_name}.m3u8"
    if not m3u_path.exists():
        # Fallback to old root structure
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
