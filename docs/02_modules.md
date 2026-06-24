# Module Reference

Detailed breakdown of every source file in the project.

---

## `app.py` — FastAPI Web Server

**Purpose**: The HTTP/WebSocket server that serves the dashboard, streams video, and exposes control APIs.

**Key Components**:
- `lifespan()` — async context manager handling startup (launches pipelines + broadcast task) and shutdown (stops all pipelines, cancels broadcast)
- `start_pipelines()` — reads `config.yaml` and spawns one `Pipeline` thread per stream
- `broadcast_events()` — background async task that pulls events from a thread-safe queue and pushes them to all connected WebSocket clients
- `generate_mjpeg(stream_id)` — generator yielding JPEG frames as MJPEG multipart response

**Endpoints**:
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves `static/index.html` |
| GET | `/video/{stream_id}` | MJPEG video stream for a camera |
| WS | `/ws/events` | WebSocket for real-time intrusion alerts |
| POST | `/api/roi` | Live-update ROI polygon for a stream |
| POST | `/api/toggle-motion` | Toggle split-screen motion view on/off |
| POST | `/api/shutdown` | Clean server shutdown (delayed SIGINT) |

**Global State**:
- `config` — parsed YAML config (dict)
- `event_queue` — thread-safe `queue.Queue` bridging pipeline threads → async broadcast
- `pipelines` — dict of `stream_id → Pipeline` instances
- `scheduler` — shared `BatchScheduler` instance
- `connected_websockets` — set of active WebSocket connections

---

## `pipeline.py` — Per-Stream Worker Thread

**Purpose**: The core orchestration engine. One instance per camera. Runs the 2-tier detection pipeline in a background thread.

**Class**: `Pipeline(threading.Thread)`

**Constructor Parameters**: `stream_id`, `config`, `scheduler`, `event_queue`

**Key Instance Variables**:
- `self.source` — video source (int for webcam, string for file/URL)
- `self.roi_percents` — ROI polygon as percentage coordinates (or None)
- `self.show_motion` — boolean controlling split-screen vs color-only output
- `self.alerted_ids` — set of track_ids that have already triggered ROI intrusion alerts
- `self.track_history` — dict of `track_id → [points]` for tripwire crossing detection
- `self.latest_frame` — most recent encoded JPEG bytes (read by MJPEG generator)

**`run()` Method Flow** (per frame):
1. Read frame from `cv2.VideoCapture`
2. Convert ROI percentages → pixel coordinates
3. Run `MotionDetector.check_motion(frame, roi_pixels)` every N frames
4. Render left pane (grayscale motion mask + blue bounding boxes)
5. Render right pane (color frame + ROI polygon overlay)
6. If motion detected → acquire GPU slot → run `Detector.detect_and_track(frame)`
7. Filter detections to ROI polygon via `cv2.pointPolygonTest`
8. **ROI Mode**: fire intrusion event for any NEW track_id inside ROI
9. **Tripwire Mode** (fallback when no ROI): fire event on line crossing
10. Log intrusion to `logs/intrusions.log`
11. Push event to `event_queue` for WebSocket broadcast
12. Annotate right pane with bounding boxes (green=human, orange=animal)
13. Combine panes via `np.hstack` (or just right pane if motion view is off)
14. Encode to JPEG → store in `self.latest_frame`

**Runtime Update Methods**:
- `update_roi(roi_percents)` — change ROI polygon without restart
- `set_show_motion(show)` — toggle split-screen view
- `stop()` — signal thread to exit

---

## `motion.py` — Tier-1 CPU Motion Detector

**Purpose**: Lightweight background subtraction to detect motion. Runs on CPU only. Acts as a gate to prevent unnecessary GPU usage.

**Class**: `MotionDetector`

**Constructor**: `MotionDetector(threshold=500)`
- `threshold` — minimum contour area in pixels to count as "real" motion

**Method**: `check_motion(frame, roi_pixels=None) → (has_motion, fg_mask, boxes)`
1. Convert frame to grayscale
2. Apply MOG2 background subtractor
3. **If ROI provided**: create binary mask via `cv2.fillPoly`, apply `cv2.bitwise_and` to zero out motion outside the polygon
4. Threshold to binary (kills MOG2 shadow pixels at 127)
5. Morphological open (removes small noise like leaves)
6. Find contours, filter by area threshold
7. Return: boolean, foreground mask, list of bounding boxes

---

## `detector.py` — Tier-2 GPU Object Detector

**Purpose**: GPU-accelerated object detection and tracking using YOLOv11.

**Class**: `Detector`

**Constructor**: `Detector(stream_id, model_path="yolo11n.pt", classes_of_interest=[], buckets={})`

**Methods**:
- `detect_and_track(frame) → list[dict]` — runs YOLOv11 inference with ByteTrack persistence. Returns list of detections, each containing:
  ```python
  {
      "track_id": int,        # Persistent ByteTrack ID
      "class_name": str,      # e.g. "person", "car", "dog"
      "bucket": str,          # e.g. "human", "animal", "object"
      "conf": float,          # Confidence score 0.0–1.0
      "bbox": [x1, y1, x2, y2],  # Bounding box
      "point": (x, y)         # Bottom-center of bbox (foot position)
  }
  ```
- `get_bucket(class_name) → str` — maps YOLO class names to configured buckets. Returns `"object"` as default fallback.

---

## `batch_scheduler.py` — GPU Access Throttle

**Purpose**: Prevents multiple camera threads from overwhelming the GPU simultaneously.

**Class**: `BatchScheduler`

**Constructor**: `BatchScheduler(max_concurrent=4)`

**Methods**:
- `acquire_slot(stream_id, priority=0) → bool` — non-blocking attempt to acquire a semaphore slot
- `release_slot(stream_id)` — release the slot back

**Implementation**: Uses `threading.Semaphore(max_concurrent)`. The `acquire` is non-blocking (`blocking=False`) so if the GPU is full, the pipeline simply skips AI detection that frame rather than blocking.

---

## `tripwire.py` — Virtual Line-Crossing Detector

**Purpose**: Detects when a tracked object crosses a virtual line (used as fallback when no ROI is set).

**Class**: `Tripwire`

**Constructor**: `Tripwire(p1, p2)` — two points defining the line

**Method**: `update(track_id, prev_point, curr_point) → str|None`
- Returns `"left_to_right"`, `"right_to_left"`, or `None`
- Uses cross-product sign change to detect line crossing

---

## `config.yaml` — Configuration File

See [04_config.md](./04_config.md) for full reference.

---

## `static/index.html` — Web Dashboard

**Purpose**: The entire frontend UI — a single-page application with no build step.

**Key Sections**:
1. **CSS** — Dark theme, glassmorphism toolbar, animated banners, toggle button states
2. **Video Grid** — 2x2 grid of `<img>` tags pointing to MJPEG endpoints
3. **ROI Drawing Engine** (JavaScript):
   - Per-camera state storage (`cameraROIs` object)
   - HTML5 Canvas overlay on each video feed
   - Click to place points, double-click to close polygon
   - Live mouse-follow preview with dashed lines
   - Green dot on first point as close hint
   - Auto-pushes completed ROI to `/api/roi` endpoint
   - Delete button per camera to clear ROI
4. **Sound System** (Web Audio API):
   - `playAlarm(bucket)` generates distinct tones:
     - `human`: sawtooth siren alternating 800–1200Hz
     - `animal`: two sine chirps descending 1400→900Hz
     - `object`: triangle wave pulse 220→160Hz
   - Gated behind `soundEnabled` boolean toggle
5. **WebSocket Event Feed**:
   - Color-coded alerts: red=human, orange=animal, blue=object
   - Icons: 🚨 human, 🐾 animal, 📦 object
   - Dynamic banner overlay on the camera that triggered the alert
6. **Control Buttons**:
   - 🔊 Sound On/Off — toggles `soundEnabled`
   - 👁 Motion View — calls `/api/toggle-motion`
   - ✏️ Draw ROI — enters/exits drawing mode
   - ⏻ Power Off — confirmation → calls `/api/shutdown`

---

## `requirements.txt` — Dependencies

```
fastapi
uvicorn
opencv-python
ultralytics
numpy
pyyaml
```
