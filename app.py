import asyncio
import os
import json
import signal
import queue
import time
import logging
import yaml
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from contextlib import asynccontextmanager

from batch_scheduler import BatchScheduler
from pipeline import Pipeline
from events_store import EventStore

# Load configuration
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

sys_cfg = config.get('system', {})

# Global State
event_queue = queue.Queue()
pipelines = {}
event_store = EventStore(path="logs/events.jsonl")
scheduler = BatchScheduler(
    max_slots=sys_cfg.get('max_batch_size', 4),
    min_slots=sys_cfg.get('min_slots', 1),
    gpu_high=sys_cfg.get('gpu_high', 85),
    gpu_low=sys_cfg.get('gpu_low', 60),
    cpu_high=sys_cfg.get('cpu_high', 90),
    cpu_low=sys_cfg.get('cpu_low', 70),
)
connected_websockets = set()
broadcast_task = None

# Runtime ROI overrides live here (so config.yaml is never rewritten/clobbered)
ROI_FILE = "runtime/roi_overrides.json"


def apply_roi_overrides():
    """Load saved ROI overrides and merge them onto the in-memory config at startup."""
    try:
        if os.path.exists(ROI_FILE):
            with open(ROI_FILE) as f:
                overrides = json.load(f)
            for sid, roi in overrides.items():
                if sid in config.get('streams', {}):
                    config['streams'][sid]['roi'] = roi
            print(f"[roi] applied {len(overrides)} saved override(s)")
    except Exception as e:
        print(f"[roi] failed to load overrides: {e}")


def save_roi_override(stream_id, roi):
    os.makedirs(os.path.dirname(ROI_FILE), exist_ok=True)
    data = {}
    if os.path.exists(ROI_FILE):
        try:
            with open(ROI_FILE) as f:
                data = json.load(f)
        except Exception:
            data = {}
    if roi is None:
        data.pop(stream_id, None)
    else:
        data[stream_id] = roi
    with open(ROI_FILE, "w") as f:
        json.dump(data, f, indent=2)


def start_pipelines():
    """Starts a worker thread for each configured stream"""
    for stream_id in config['streams']:
        p = Pipeline(stream_id, config, scheduler, event_queue)
        p.start()
        pipelines[stream_id] = p


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    apply_roi_overrides()
    start_pipelines()
    global broadcast_task
    broadcast_task = asyncio.create_task(broadcast_events())
    yield
    # Shutdown
    for p in pipelines.values():
        p.stop()
    for p in pipelines.values():
        p.join(timeout=3)
    if broadcast_task:
        broadcast_task.cancel()
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve saved intrusion snapshots (evidence)
os.makedirs("snapshots", exist_ok=True)
app.mount("/snapshots", StaticFiles(directory="snapshots"), name="snapshots")

# Serve recorded incident clips (footage)
os.makedirs("clips", exist_ok=True)
app.mount("/clips", StaticFiles(directory="clips"), name="clips")


async def broadcast_events():
    """Push queue events to WebSocket clients; persist completed incidents."""
    while True:
        sent_any = False
        try:
            while True:
                event = event_queue.get_nowait()
                if event.get("type") == "incident":
                    event_store.add(event)
                disconnected = set()
                for ws in connected_websockets:
                    try:
                        await ws.send_json(event)
                    except Exception:
                        disconnected.add(ws)
                for ws in disconnected:
                    connected_websockets.discard(ws)
                sent_any = True
        except queue.Empty:
            pass
        await asyncio.sleep(0.02 if sent_any else 0.05)


@app.get("/")
def read_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(f.read())


def generate_mjpeg(stream_id):
    pipeline = pipelines.get(stream_id)
    try:
        while pipeline and pipeline.running:
            frame = pipeline.latest_frame
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                time.sleep(0.1)
            time.sleep(0.03)
    except GeneratorExit:
        pass


@app.get("/video/{stream_id}")
def video_feed(stream_id: str):
    return StreamingResponse(generate_mjpeg(stream_id),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/events")
def api_events(limit: int = 100):
    """Completed incident history (newest first)."""
    return JSONResponse(event_store.list(limit))


@app.get("/api/stats")
def api_stats():
    """Live system load + per-camera health for the dashboard."""
    now = time.time()
    return JSONResponse({
        "load": scheduler.stats(now),
        "streams": {sid: p.health(now) for sid, p in pipelines.items()},
    })


@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        connected_websockets.discard(websocket)


class ROIUpdate(BaseModel):
    stream_id: str
    roi: Optional[List[List[float]]] = None


@app.post("/api/roi")
async def update_roi(data: ROIUpdate):
    """Live-update ROI for a running stream; persist to the runtime override file."""
    pipeline = pipelines.get(data.stream_id)
    if not pipeline:
        return {"error": f"Stream {data.stream_id} not found"}
    pipeline.update_roi(data.roi)
    save_roi_override(data.stream_id, data.roi)
    return {"status": "ok", "stream_id": data.stream_id}


@app.post("/api/toggle-motion")
async def toggle_motion(show: bool = True):
    for p in pipelines.values():
        p.set_show_motion(show)
    return {"status": "ok", "show_motion": show}


@app.post("/api/shutdown")
async def shutdown_system():
    async def _delayed_kill():
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)
    asyncio.create_task(_delayed_kill())
    return {"status": "shutting down"}


if __name__ == "__main__":
    logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")
