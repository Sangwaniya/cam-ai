# 02 — Architecture & Decisions

This is the **decided** production architecture and the rationale behind each choice. The demo simplifies it (doc 03), but build with this end-state in mind.

## Core principle: parallel, read-only AI overlay
The AI subsystem is a **standalone server** that only **reads copies** of camera streams and only **emits events**. It never writes to the NVRs, never changes the VMS, never sits in the recording path. If it fails, recording and monitoring continue. This is what guarantees "no disruption."

## Two-tier sensing — how "20 of 300" works
1. **Tier 1 — Motion, on ALL enrolled cameras, always-on, cheap (CPU).** Pixel-change / background-subtraction motion detection answers "is anything moving on camera X?" for all ~300 continuously. No GPU.
2. **Tier 2 — AI, on the ≤20 cameras with activity (GPU).** When Tier 1 flags motion, a **slot manager** assigns that camera one of the ≤20 GPU slots to run YOLO detection + classification + tracking + line-crossing.

This meets "20 concurrent" honestly while never being blind to motion. **Do NOT use blind round-robin rotation** — it leaves the perimeter dark between batches and misses intrusions. Motion-gating is the correct pattern.

**Why not detect on the cameras (edge AI)?** Cheap cameras do on-device detection because each has a dedicated AI chip. The existing mixed fleet largely lacks this, can't be retrofitted, and the RFP forbids replacing cameras. So detection is centralized — and centralizing 300 *continuous* AI streams is infeasible on the budgeted hardware (video **decode** alone caps a single GPU at ~tens of streams). Hence motion-gating.

## Coverage strategy (the tiers)
- **Always-on perimeter:** pin the true fence-line cameras to permanent AI slots (no gating).
- **Motion-gated interior:** interior cameras get a slot only on motion.
- **Spare-slot sweeps:** idle slots periodically sweep quiet cameras.
- **Priority weighting:** risk/time-weighted (gates, night) slot allocation.
- **Predictive hand-off:** when an intruder nears a camera's edge, pre-assign the adjacent camera a slot to follow them along the perimeter.
- **Oversubscription handling:** if >20 cameras have simultaneous motion (e.g., a storm), prioritize perimeter > interior and log deferred cameras (auditable).

## Detection & classification
- **Model:** YOLO family (Ultralytics) — `yolo11n` for the demo; larger and/or fine-tuned for production.
- **Tracking:** **ByteTrack** (built into Ultralytics `model.track(persist=True)`), **one model / tracker instance per stream** so tracking never mixes between cameras.
- **Buckets:** map fine classes → `human` (person), `animal` (dog/cat/cow/horse/sheep/elephant/bear/…), `object` (everything else / unclassified motion).
- **Buffalo:** not a COCO class; in production **fine-tune** on local species, or accept detection as "cow". A configurable "large non-human, non-vehicle object" rule is the catch-all for "any animal ≥ dog size".
- **Tracking point:** use the **bottom-center** of the bounding box (the object's ground-contact/feet) for crossing — more accurate than the centroid.

## Line-crossing logic
- Operators draw a **virtual tripwire** (a line segment) in the **camera's image space** — *not* on the map. The map shows *which* camera fired.
- An object **crosses** when the segment between its previous and current tracking point **intersects** the tripwire segment. Direction comes from the sign of the cross product. A per-track **debounce/cooldown** prevents duplicate alerts.
- Implemented in `tripwire.py` (pure Python, unit-tested).

## False-alarm strategy — three nested filters
An alarm fires only if **all three** pass:
1. **Motion gate** — sustained, person-sized motion (min-blob-size + temporal-persistence + adaptive background model defeat leaf-flicker and gradual lighting change).
2. **AI classification** — confidently human or animal.
3. **Directional crossing** — the tracked object actually crosses the line in the relevant direction.

Swaying trees, rain, and shadows fail filters 2 and 3.

## Latency target — 1 to 2 seconds
Achieved by: keeping the model **warm** in GPU memory (slots pre-loaded), routing **live frames** (not still snapshots) to a slot, and placing the motion **wake zone on the approach side** of the line so analysis begins before the crossing. A short **look-back buffer** (a few seconds) avoids losing the start of the crossing and provides pre-event clip footage.

## Performance / capacity (turns 20 into an effective 40–60)
TensorRT compilation (2–4× speedup), FP16/INT8 quantization, **batched** multi-stream inference, **ROI-crop** inference, adaptive resolution/fps, and **NVDEC** hardware decode. The real ceiling is **video decode** (~tens of streams per GPU), which is accounted for in sizing.

## Hardware
- **One NVIDIA L4-class GPU server** for ~20 concurrent streams (CPU works for the demo, slower).
- **Second L4** for active-active high availability, if required.
- Supporting: managed switch, UPS, operator workstation(s), monitoring display(s), audio annunciator — per the BoQ.

## Software split (production)
- **Python analytics microservice** (this repo's core) — detection, tracking, crossing, motion-gating, slot manager. Stays Python.
- **Go backend** — event store (Postgres), config/zone API, slot-manager orchestration, health monitoring, reporting, VMS integration. (Owner's strength.)
- **React frontend** — the **offline map** UI: camera pins, draw zones/lines, live alerts, event review. (Owner's strength.)
- **Stream access:** RTSP **sub-stream** (low-res) via ONVIF — **direct-from-camera preferred**, **NVR (VideoEdge) re-stream** fallback.
- **Events:** thin JSON over **MQTT** (or WebSocket) — **no video** on the event bus.

## The event contract (stable seam: Python → Go → React)
Keep this schema stable; extend only additively.
```jsonc
{
 "stream_id": "cam1",
 "stream_name": "North Gate",
 "class": "person",          // fine YOLO class
 "bucket": "human",          // human | animal | object
 "direction": "A_to_B",      // crossing direction
 "conf": 0.91,
 "ts": 1719100000.123,        // unix seconds
 "snapshot": "/snapshots/cam1_1719100000123.jpg"
}
```
TypeScript (for the future React side):
```ts
type Bucket = "human" | "animal" | "object";

interface IntrusionEvent {
 stream_id: string;
 stream_name: string;
 class: string;
 bucket: Bucket;
 direction: "A_to_B" | "B_to_A";
 conf: number;     // 0..1
 ts: number;       // unix seconds
 snapshot: string; // URL
 clip?: string;    // URL (production)
}
```
