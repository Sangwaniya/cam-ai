# 04 — Codebase Guide

## What exists
A runnable Python demo. Structure:
```
pids-demo/
├── app.py            # FastAPI: MJPEG video + WebSocket alerts + serves the dashboard
├── pipeline.py       # per-stream thread: decode → detect → tripwire → annotate → events
├── detector.py       # YOLO detection + ByteTrack + human/animal/object bucketing
├── tripwire.py       # line-crossing geometry (pure Python, UNIT-TESTED)
├── config.yaml       # model, classes, streams, tripwire coordinates
├── static/index.html # dashboard (vanilla JS, no build step)
├── requirements.txt
├── AGENT_CONTEXT.md  # start-here for agents
└── docs/             # this documentation set
```

## Module responsibilities
- **`detector.py` → `Detector`**: loads a YOLO model (weights auto-download on first run), runs `model.track(persist=True, tracker="bytetrack.yaml")`, filters to `classes_of_interest`, and returns detections with `track_id`, `class_name`, `bucket`, `conf`, `bbox`, and `point` (bottom-center). `bucket_for()` maps a class → human/animal/object. **One `Detector` per stream** (independent tracker state).
- **`tripwire.py` → `Tripwire`**: holds the line segment; `update(detections, now)` returns crossing events using segment-intersection on each track's previous→current point, with direction and a per-track cooldown. **Pure Python — keep it dependency-free and tested.**
- **`pipeline.py` → `Pipeline`**: one per stream, runs in a thread. Opens the source (file/RTSP/webcam), loops frames, calls the detector + tripwire, saves snapshots, pushes events to a shared queue, annotates the frame, and keeps the latest JPEG for MJPEG. Loops video files for a continuous demo. **This is where Tier-1 motion-gating plugs in later.**
- **`app.py`**: loads config, builds a `Detector`+`Pipeline` per stream, starts them, and serves: `/` (dashboard), `/streams`, `/events`, `/video/{id}` (MJPEG), `/ws/events` (WebSocket broadcast), `/snapshots/...`. A background async task bridges the thread-fed event queue to WebSocket clients.
- **`static/index.html`**: builds a video grid from `/streams`, backfills `/events`, subscribes to `/ws/events`, renders the alert feed, and plays a WebAudio beep.

## How to run
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# edit config.yaml: set source ("0" for webcam, a file path, or an rtsp url) and tripwire coords
python app.py        # → http://localhost:8000
```
On startup the console prints each stream's frame size to help you choose tripwire coordinates.

## State of completeness
- ✅ Detection + tracking + bucketing (code complete; **needs a real run** to verify on hardware).
- ✅ Line-crossing (unit-tested).
- ✅ Dashboard, MJPEG, WebSocket alerts, snapshots, audio.
- ⏳ Not yet run end-to-end with a downloaded model + real video — **this is task T0.1–T0.3**.
- 🔌 Extension points (stubs to build later): motion-gating + slot manager (in `pipeline.py` / a new module); Go event publishing; React map; health/reporting; clips; model fine-tuning.

## Conventions
- Keep the **event JSON contract** (doc 02) stable.
- Keep `tripwire.py` dependency-free and unit-tested.
- Don't add heavy framework deps to the demo; keep `python app.py` a one-command launch.
- Comment non-obvious logic; keep modules small and readable.
