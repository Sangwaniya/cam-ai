# System Architecture

## High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CAMERA FEEDS                                  │
│   RTSP / MJPEG / Webcam / Video File                                │
└──────────────┬──────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PIPELINE (pipeline.py) — One per camera, runs in its own thread    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  TIER 1: CPU Motion Gate (motion.py)                         │    │
│  │  • Background subtraction (MOG2)                             │    │
│  │  • ROI polygon masking — ignores motion outside boundary     │    │
│  │  • Morphological filtering to kill noise                     │    │
│  │  • If motion detected → request GPU slot                     │    │
│  │  • If NO motion → GPU stays asleep (saves power)             │    │
│  └──────────────────────┬───────────────────────────────────────┘    │
│                         │ motion detected                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  BATCH SCHEDULER (batch_scheduler.py)                        │    │
│  │  • Semaphore limits concurrent GPU threads                   │    │
│  │  • Prevents GPU memory exhaustion on multi-cam setups        │    │
│  └──────────────────────┬───────────────────────────────────────┘    │
│                         │ slot acquired                              │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  TIER 2: GPU AI Scanner (detector.py)                        │    │
│  │  • YOLOv11 Nano inference                                    │    │
│  │  • ByteTrack multi-object tracking (persistent IDs)          │    │
│  │  • Class → Bucket mapping (person→human, dog→animal, etc.)   │    │
│  │  • ROI polygon filtering (cv2.pointPolygonTest)              │    │
│  └──────────────────────┬───────────────────────────────────────┘    │
│                         │ detections inside ROI                      │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  EVENT FIRING                                                 │    │
│  │  • ROI Mode: new track_id inside ROI → instant intrusion     │    │
│  │  • Tripwire Mode (fallback): line crossing → intrusion       │    │
│  │  • Logs to logs/intrusions.log                               │    │
│  │  • Pushes event to FastAPI event queue                       │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  FRAME RENDERING                                                     │
│  • Left pane: grayscale motion mask + blue motion blobs             │
│  • Right pane: color video + green/orange bounding boxes + ROI      │
│  • Combined via np.hstack → MJPEG stream                           │
│  • Motion view can be toggled off (color-only mode)                 │
└──────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FASTAPI SERVER (app.py)                                             │
│                                                                      │
│  • GET /              → Serves the HTML dashboard                   │
│  • GET /video/{id}    → MJPEG stream per camera                     │
│  • WS  /ws/events     → Pushes intrusion events to all browsers    │
│  • POST /api/roi      → Live-update ROI for a stream (no restart)  │
│  • POST /api/toggle-motion → Show/hide split-screen motion view    │
│  • POST /api/shutdown → Clean server shutdown from UI               │
└──────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  WEB DASHBOARD (static/index.html)                                   │
│                                                                      │
│  • 2x2 video grid with live MJPEG feeds                             │
│  • Interactive ROI drawing tool (HTML5 Canvas)                      │
│  •   — Click to place points, double-click to close polygon         │
│  •   — Per-camera storage, delete individual ROIs                   │
│  •   — Auto-pushes to backend API (enforced immediately)            │
│  • Sound toggle (mute/unmute alarm sounds)                          │
│  • Motion view toggle (split-screen vs color-only)                  │
│  • Power Off button (clean shutdown with confirmation)              │
│  • Live Event Feed with color-coded intrusion alerts                │
│  • Web Audio API alarm sounds (distinct per bucket type)            │
│  •   — Human: rising siren    Animal: double chirp                  │
│  •   — Object: deep warning pulse                                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Design Principles

1. **CPU-first, GPU-on-demand**: The motion detector runs on CPU at all times. The GPU only wakes up when there's actual motion. This saves enormous power on multi-camera deployments.

2. **Thread-per-stream**: Each camera feed runs in its own Python thread. This isolates failures — if one camera drops, the others keep running.

3. **Semaphore-based GPU scheduling**: A counting semaphore (`batch_scheduler.py`) limits how many threads can use the GPU simultaneously, preventing CUDA out-of-memory crashes.

4. **ROI as the primary security primitive**: The user draws a polygon on the dashboard. This polygon is enforced at BOTH tiers:
   - Tier 1: motion pixels outside the polygon are zeroed out
   - Tier 2: YOLO detections with center points outside the polygon are discarded

5. **Live configuration**: ROI changes are pushed via API and take effect within 1 frame. No server restart needed.

6. **Resolution-independent coordinates**: ROI polygons are stored as percentages (0.0–1.0) of the frame dimensions. This means they work correctly even if the video resolution changes.
