# Configuration Reference

All configuration is in `config.yaml` at the project root.

---

## `system` — Global System Settings

```yaml
system:
  max_batch_size: 4       # Max simultaneous GPU inference threads
  motion_threshold: 500   # Min contour area (pixels²) to count as motion
  motion_fps: 5           # How often to run CPU motion check (frames per second)
  log_level: "INFO"       # Logging level
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_batch_size` | int | 4 | Controls the `BatchScheduler` semaphore. Set higher for production GPUs (e.g., 16 on L4, 32 on A100). |
| `motion_threshold` | int | 500 | Minimum contour area in pixels² for a motion blob to be considered real. Lower = more sensitive (but more false positives). Higher = less sensitive. |
| `motion_fps` | int | 5 | The CPU motion detector runs at this FPS regardless of the video's native FPS. At 30fps video, setting this to 5 means motion is checked every 6th frame. |
| `log_level` | string | "INFO" | Python logging level. |

---

## `classes_of_interest` — What to Detect

A flat list of YOLO class names the system should detect. Anything not in this list is ignored by the GPU detector even if YOLO sees it.

```yaml
classes_of_interest:
  - "person"
  - "dog"
  - "cat"
  - "cow"
  - "car"
  - "truck"
  # ... etc.
```

**Currently configured**: person, dog, cat, cow, horse, sheep, elephant, bear, zebra, giraffe, car, truck, motorcycle, bicycle, bus, boat, backpack, suitcase

**All valid values**: Any class from the [COCO 80-class list](https://docs.ultralytics.com/datasets/detect/coco/) that YOLOv11 supports.

---

## `buckets` — Detection Categories

Maps fine-grained YOLO classes into broad categories. Each bucket gets its own alarm sound and alert color in the dashboard.

```yaml
buckets:
  human:
    - "person"
  animal:
    - "dog"
    - "cat"
    - "cow"
  object:
    - "car"
    - "truck"
    - "backpack"
```

| Bucket | Dashboard Color | Alarm Sound | Icon |
|--------|----------------|-------------|------|
| `human` | Red | Rising siren (sawtooth 800–1200Hz) | 🚨 |
| `animal` | Orange | Double chirp (sine 1400→900Hz) | 🐾 |
| `object` | Blue | Deep pulse (triangle 220→160Hz) | 📦 |

**Fallback**: Any `class_of_interest` not assigned to a bucket defaults to `"object"`.

---

## `streams` — Camera Configuration

Each key under `streams` is a unique stream ID. The dashboard currently supports up to 4 (hardcoded in `index.html`).

```yaml
streams:
  cam1:
    name: "North Gate"
    source: "rtsp://admin:pass@192.168.1.100/stream"
    priority: 10
    tripwire: [[380, -1000], [380, 2000]]
    roi: [[0.2, 0.1], [0.8, 0.1], [0.8, 0.9], [0.2, 0.9]]
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | Yes | Human-readable name shown in dashboard and logs |
| `source` | string/int | Yes | Video source. Can be: `"0"` (local webcam), a file path (`"test_video.mp4"`), an RTSP URL, or an MJPEG HTTP URL |
| `priority` | int | Yes | Higher = higher priority for GPU scheduling. **Note**: Currently accepted but not used by the scheduler. |
| `tripwire` | list | Yes | Two `[x, y]` points defining the virtual tripwire line. Used only when no ROI is set. |
| `roi` | list | No | Polygon vertices as `[x%, y%]` pairs (0.0–1.0 relative to frame size). If set, the system operates in ROI breach mode instead of tripwire mode. Can be set/cleared live via the dashboard. |

### Source Formats

```yaml
# Local webcam
source: "0"

# Local video file (loops automatically)
source: "test_video.mp4"

# RTSP IP camera
source: "rtsp://admin:password@192.168.1.100:554/stream"

# MJPEG HTTP stream
source: "http://camera.example.com/mjpg/video.mjpg"
```

### ROI Coordinates

ROI coordinates are **resolution-independent percentages** (0.0 to 1.0):
- `[0.0, 0.0]` = top-left corner
- `[1.0, 1.0]` = bottom-right corner
- `[0.5, 0.5]` = center of frame

The polygon is converted to pixel coordinates at runtime based on the actual frame dimensions. This means the same ROI works even if video resolution changes.

**Minimum 3 points** required to form a valid polygon.

---

## Intrusion Log Format

All intrusion events are appended to `logs/intrusions.log`:

```
[2024-06-24 17:25:42] INTRUSION | stream=cam3 | name=Worker Zone | bucket=human | class=person | direction=roi_breach | confidence=0.892 | track_id=7
```

Fields are pipe-delimited for easy parsing with `grep`, `awk`, or log aggregation tools.
