# Project Status — What's Been Built

Last updated: 2024-06-24

---

## ✅ Implemented Features

### Core Detection Pipeline
- [x] **2-tier CPU→GPU architecture** — CPU motion gate prevents unnecessary GPU usage
- [x] **YOLOv11 Nano inference** — real-time object detection with `yolo11n.pt`
- [x] **ByteTrack multi-object tracking** — persistent track IDs across frames
- [x] **3-class detection buckets** — human (person), animal (9 species), object (8 types including vehicles)
- [x] **ROI polygon masking** — motion detector ignores pixels outside the drawn boundary
- [x] **ROI-filtered GPU detections** — YOLO detections outside the polygon are discarded via `cv2.pointPolygonTest`
- [x] **ROI breach intrusion mode** — any NEW object inside ROI triggers alert (no tripwire crossing required)
- [x] **Tripwire fallback mode** — virtual line-crossing detection when no ROI is set
- [x] **Adaptive GPU batching** — semaphore limits concurrent GPU access to prevent OOM

### Web Dashboard
- [x] **4-camera grid** — simultaneous MJPEG feeds in a 2×2 layout
- [x] **Interactive ROI drawing** — click-to-draw polygon on live video, double-click to close
- [x] **Per-camera ROI management** — independent polygons, delete individual zones
- [x] **Live ROI push** — drawn boundaries enforced immediately via API (no restart)
- [x] **Sound toggle** — mute/unmute alarm sounds from dashboard
- [x] **Motion view toggle** — switch between split-screen (debug) and color-only view
- [x] **Power Off button** — clean system shutdown from the browser
- [x] **Distinct alarm sounds** — siren (human), chirp (animal), deep pulse (object) via Web Audio API
- [x] **Color-coded alerts** — red/orange/blue banners and event feed entries per bucket type
- [x] **Live Event Feed** — WebSocket-powered scrolling log with icons and confidence scores

### Logging & Persistence
- [x] **File-based intrusion logging** — every event logged to `logs/intrusions.log`
- [x] **Config persistence** — ROI changes auto-saved to `config.yaml`

---

## ⚠️ Known Limitations / Not Yet Implemented

### Dashboard
- [ ] **Camera cards are hardcoded** — HTML has 4 static cards. Adding/removing cameras requires editing both `config.yaml` and `index.html`. A dynamic approach reading from a `/api/streams` endpoint would be better.
- [ ] **Camera name mismatch** — some HTML labels don't match config names (e.g., cam3 shows "Worker Zone" in HTML but "Pedestrian Walkway" in config after a yaml dump rewrite)
- [ ] **No snapshot images** — alert feed shows text-only events. The architecture doc specifies snapshot evidence per alert.
- [ ] **Google Fonts dependency** — dashboard loads Inter font from Google Fonts (needs internet). Could be bundled for offline deployments.

### Backend
- [ ] **Priority scheduling not implemented** — `BatchScheduler.acquire_slot()` accepts a `priority` parameter but ignores it. Slots are first-come-first-served.
- [ ] **No per-stream slot tracking** — scheduler doesn't know which stream holds which slot
- [ ] **No snapshot file saving** — frames are passed in the event queue but never written to disk as evidence images
- [ ] **No health monitoring** — no heartbeat/status endpoint to check if streams are alive
- [ ] **No `/api/streams` endpoint** — the dashboard can't dynamically discover configured cameras
- [ ] **Tripwire has no cooldown** — once a track crosses, it's permanently debounced (can never re-trigger)

### Production Readiness
- [ ] **No Go backend** — production plan calls for Go (currently Python-only)
- [ ] **No React map view** — production plan calls for a React frontend with an offline map
- [ ] **No VMS integration** — no connection to existing Video Management Systems
- [ ] **No High Availability** — single server, no failover
- [ ] **No model fine-tuning** — using stock YOLO weights (no custom training for local species)
- [ ] **No RTSP re-streaming** — no ability to republish processed feeds

---

## 🗂 Test Assets

| File | Size | Content |
|------|------|---------|
| `test_video.mp4` | 5.7 MB | Intel pedestrian crossing — people walking in a parking lot |
| `test_video_2.mp4` | 5.2 MB | Intel people detection — staircase/subway scene |
| `test_video_3.mp4` | 12.0 MB | Intel worker zone — wide open industrial warehouse floor |
| `test_video_4.mp4` | 6.1 MB | Intel face demographics — hallway walking scene |
| `yolo11n.pt` | 5.3 MB | YOLOv11 Nano pre-trained weights (COCO 80-class) |

---

## 📁 File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | ~156 | FastAPI server, routes, WebSocket, APIs |
| `pipeline.py` | ~222 | Per-stream worker thread, 2-tier detection, frame rendering |
| `motion.py` | ~47 | CPU motion detector with ROI masking |
| `detector.py` | ~54 | GPU YOLO detector + ByteTrack + bucket mapping |
| `batch_scheduler.py` | ~32 | Semaphore-based GPU access control |
| `tripwire.py` | ~37 | Virtual line-crossing detector |
| `config.yaml` | ~100 | System, stream, class, and bucket configuration |
| `static/index.html` | ~605 | Complete dashboard UI |
| `requirements.txt` | ~7 | Python dependencies |

---

## 🏗 Original Roadmap Progress

From the original phased plan:

| Phase | Task | Status |
|-------|------|--------|
| Phase 0 | Baseline install + verify | ✅ Done |
| Phase 1 | Detection, tracking, tripwire, dashboard | ✅ Done |
| Phase 1 | Two-camera demo | ✅ Done (4 cameras) |
| Phase 1 | Animal classification | ✅ Done (9 species) |
| Phase 1 | Dashboard polish | ✅ Done (modern dark UI, toggles, drawing) |
| Phase 2 | Tier-1 motion detector | ✅ Done (`motion.py`) |
| Phase 2 | Slot manager | ✅ Done (`batch_scheduler.py`) |
| Phase 2 | N-of-M camera demo | ✅ Done (4 simultaneous) |
| Phase 3 | Go backend | ❌ Not started |
| Phase 3 | React map UI | ❌ Not started |
| Phase 3 | RTSP integration | ❌ Not started |
| Phase 3 | Health monitoring | ❌ Not started |
| Phase 3 | Model fine-tuning | ❌ Not started |
| Phase 3 | High availability | ❌ Not started |
