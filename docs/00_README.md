# Camai — Perimeter Intrusion Detection System (PIDS)

## What Is This?

Camai is an AI-powered **Perimeter Intrusion Detection System** built for real-time security surveillance. It processes live camera feeds (RTSP, MJPEG, local webcam, or video files), detects humans, animals, and objects using GPU-accelerated AI (YOLOv11), and raises instant audio+visual alerts when something enters a user-defined security zone.

## Key Capabilities

| Feature | Description |
|---------|-------------|
| **Multi-Camera Support** | Process 4+ simultaneous video streams |
| **2-Tier Detection Pipeline** | CPU motion gate → GPU AI scanner (saves GPU cycles) |
| **ROI Boundary Drawing** | Users draw custom security zones directly on the live dashboard |
| **Live ROI Enforcement** | ROI updates push to the backend instantly — no restart needed |
| **3-Class Detection** | Humans 🚨, Animals 🐾, Objects/Vehicles 📦 — each with distinct alarm sounds |
| **Intrusion Logging** | Every breach is logged to `logs/intrusions.log` with full metadata |
| **Split-Screen Debug View** | Left pane shows CPU motion mask, right pane shows AI detections |
| **Toggleable UI Controls** | Sound on/off, Motion view on/off, Draw ROI, Power Off — all from the dashboard |
| **Adaptive GPU Batching** | Concurrent GPU access is throttled to prevent memory exhaustion |

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
python app.py

# 4. Open the dashboard
open http://localhost:8000
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn, OpenCV, Ultralytics YOLOv11, NumPy
- **Frontend**: Vanilla HTML5/CSS/JS, Web Audio API, Canvas API, WebSocket
- **AI Model**: `yolo11n.pt` (YOLOv11 Nano) with ByteTrack for object tracking
- **Streaming**: MJPEG over HTTP for video, WebSocket for real-time event push

## Project Structure

```
Camai/
├── app.py                 # FastAPI web server — routes, WebSocket, API endpoints
├── pipeline.py            # Per-stream worker thread — orchestrates Tier-1 → Tier-2
├── motion.py              # Tier-1 CPU motion detector (background subtraction + ROI masking)
├── detector.py            # Tier-2 GPU object detector (YOLOv11 + ByteTrack)
├── batch_scheduler.py     # Semaphore-based GPU access throttle
├── tripwire.py            # Virtual tripwire line-crossing detector
├── config.yaml            # All configuration — streams, classes, buckets, ROI
├── requirements.txt       # Python dependencies
├── yolo11n.pt             # Pre-trained YOLOv11 Nano model weights
├── static/
│   └── index.html         # Full dashboard UI — drawing tool, toggles, event feed
├── logs/
│   └── intrusions.log     # Persistent intrusion event log
├── docs/                  # This documentation folder
│   ├── 00_README.md       # ← You are here
│   ├── 01_architecture.md # System architecture and data flow
│   ├── 02_modules.md      # Detailed module-by-module reference
│   ├── 03_api.md          # API endpoint documentation
│   ├── 04_config.md       # Configuration reference
│   └── 05_status.md       # Current status and what's been implemented
└── test_video*.mp4        # Sample test videos for development
```

## For AI Assistants

If you are an AI tool picking up this project, start with:
1. **[05_status.md](./05_status.md)** — What has been built, what works, what's next
2. **[01_architecture.md](./01_architecture.md)** — How the whole system fits together
3. **[02_modules.md](./02_modules.md)** — Every file, class, function, and line reference
4. **[03_api.md](./03_api.md)** — All HTTP/WebSocket endpoints
5. **[04_config.md](./04_config.md)** — How to configure streams, ROI, classes, and system tuning
