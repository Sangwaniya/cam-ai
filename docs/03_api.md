# API Reference

All HTTP and WebSocket endpoints exposed by the FastAPI server (`app.py`).

Base URL: `http://localhost:8000`

---

## Pages

### `GET /`
Serves the dashboard HTML from `static/index.html`.

### `GET /video/{stream_id}`
Returns an MJPEG video stream for the specified camera.

**Parameters**: `stream_id` — camera identifier (e.g., `cam1`, `cam2`)

**Response**: `multipart/x-mixed-replace; boundary=frame` — continuous JPEG frames

**Notes**: The stream is either a split-screen (motion mask + color) or color-only, depending on the motion view toggle state.

---

## WebSocket

### `WS /ws/events`
Real-time intrusion event stream. The server pushes JSON events to all connected clients.

**Event Schema**:
```json
{
    "stream_id": "cam1",
    "stream_name": "Intersection Crossing",
    "class": "person",
    "bucket": "human",
    "direction": "roi_breach",
    "conf": 0.892,
    "ts": 1719234567.89
}
```

**Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `stream_id` | string | Camera identifier from config |
| `stream_name` | string | Human-readable camera name |
| `class` | string | YOLO class name (e.g., `person`, `dog`, `car`) |
| `bucket` | string | Category: `human`, `animal`, or `object` |
| `direction` | string | `roi_breach` (ROI mode) or `left_to_right`/`right_to_left` (tripwire mode) |
| `conf` | float | Detection confidence (0.0–1.0) |
| `ts` | float | Unix timestamp of the event |

---

## REST APIs

### `POST /api/roi`
Live-update the ROI (Region of Interest) polygon for a running camera stream. Takes effect immediately on the next frame — no restart needed. Also persists the change to `config.yaml`.

**Request Body** (JSON):
```json
{
    "stream_id": "cam1",
    "roi": [[0.2, 0.1], [0.8, 0.1], [0.8, 0.9], [0.2, 0.9]]
}
```

**Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `stream_id` | string | Camera identifier |
| `roi` | `list[list[float]]` or `null` | Polygon vertices as [x%, y%] pairs (0.0–1.0). Pass `null` to clear the ROI. |

**Response**: `{"status": "ok", "stream_id": "cam1"}`

---

### `POST /api/toggle-motion`
Toggle the split-screen motion view on or off for all cameras.

**Query Parameter**: `show` — `true` (split-screen) or `false` (color-only)

**Example**: `POST /api/toggle-motion?show=false`

**Response**: `{"status": "ok", "show_motion": false}`

---

### `POST /api/shutdown`
Cleanly shut down the entire system. Stops all pipeline threads, closes video captures, and kills the server process.

**Request Body**: None

**Response**: `{"status": "shutting down"}`

**Notes**: The server sends a delayed SIGINT to itself so the HTTP response completes before the process exits.

---

## Static Files

### `GET /static/{path}`
Serves files from the `static/` directory. Currently only contains `index.html`.
