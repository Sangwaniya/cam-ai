import asyncio
import os
import signal
import queue
import time
import logging
import yaml
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from batch_scheduler import BatchScheduler
from pipeline import Pipeline

from contextlib import asynccontextmanager

# Load configuration
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Global State
event_queue = queue.Queue()
pipelines = {}
scheduler = BatchScheduler(max_concurrent=config.get('system', {}).get('max_batch_size', 4))
connected_websockets = set()
broadcast_task = None

def start_pipelines():
    """Starts a worker thread for each configured stream"""
    for stream_id, stream_config in config['streams'].items():
        p = Pipeline(stream_id, config, scheduler, event_queue)
        p.start()
        pipelines[stream_id] = p

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_pipelines()
    global broadcast_task
    broadcast_task = asyncio.create_task(broadcast_events())
    yield
    # Shutdown
    for p in pipelines.values():
        p.stop()
        p.join()
    if broadcast_task:
        broadcast_task.cancel()

app = FastAPI(lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

async def broadcast_events():
    """Background task to push queue events to all connected WebSocket clients"""
    while True:
        try:
            # Non-blocking pull from the event queue
            event, frame = event_queue.get_nowait()
            
            disconnected = set()
            for ws in connected_websockets:
                try:
                    await ws.send_json(event)
                except Exception:
                    disconnected.add(ws)
            
            for ws in disconnected:
                connected_websockets.remove(ws)
                
        except queue.Empty:
            pass
        
        await asyncio.sleep(0.05)

@app.get("/")
def read_root():
    """Serve the dashboard"""
    with open("static/index.html", "r") as f:
        return HTMLResponse(f.read())

def generate_mjpeg(stream_id):
    """Yield JPEG bytes for the MJPEG video stream"""
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
    """MJPEG streaming endpoint"""
    return StreamingResponse(generate_mjpeg(stream_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """Client endpoint to listen for real-time intrusion events"""
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)


class ROIUpdate(BaseModel):
    stream_id: str
    roi: Optional[List[List[float]]] = None

@app.post("/api/roi")
async def update_roi(data: ROIUpdate):
    """Live-update ROI for a running stream without restart"""
    pipeline = pipelines.get(data.stream_id)
    if not pipeline:
        return {"error": f"Stream {data.stream_id} not found"}
    pipeline.update_roi(data.roi)
    # Also persist to config.yaml
    config['streams'][data.stream_id]['roi'] = data.roi
    with open('config.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    return {"status": "ok", "stream_id": data.stream_id}

@app.post("/api/toggle-motion")
async def toggle_motion(show: bool = True):
    """Toggle the split-screen motion view for all streams"""
    for p in pipelines.values():
        p.set_show_motion(show)
    return {"status": "ok", "show_motion": show}

@app.post("/api/shutdown")
async def shutdown_system():
    """API endpoint to cleanly shut down the server.
    Delays SIGINT briefly so the HTTP response can complete."""
    async def _delayed_kill():
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)
    asyncio.create_task(_delayed_kill())
    return {"status": "shutting down"}

if __name__ == "__main__":
    # Suppress noisy CancelledError tracebacks during shutdown
    logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")
