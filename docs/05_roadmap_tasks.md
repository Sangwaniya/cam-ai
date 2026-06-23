# 05 — Roadmap & Tasks

Work top-down. Each task has acceptance criteria. **Phases 0–1 deliver the demo. Phase 2 is the high-value stretch. Phase 3 is production.** Tick boxes as you go and note assumptions inline.

## Phase 0 — Get the baseline running (do this first)
- [ ] **T0.1 Install & launch.** Create a venv, install requirements, run `python app.py`, confirm it starts and the model downloads.
 - *Done when:* the dashboard loads at `localhost:8000` with no errors.
- [ ] **T0.2 Verify the full loop with a webcam.** Set `source: "0"` in `config.yaml`; walk across the line.
 - *Done when:* you get a `person/human` box, the line flashes, an INTRUSION banner appears, a feed alert with a snapshot is added, and a beep plays — within ~1–2 s of crossing.
- [ ] **T0.3 Verify with a video file.** Use a perimeter / CCTV-style clip; set the tripwire to match the scene.
 - *Done when:* crossings in the clip reliably alert; no crashes over a multi-minute loop.

## Phase 1 — Make the demo presentation-ready
- [ ] **T1.1 Tune to the client footage.** Obtain a clip from the client's cameras if possible; set the tripwire coordinates; tune `conf` and `classes_of_interest` to minimize false alarms while still catching real crossings.
 - *Done when:* on the demo footage, real crossings alert and idle scenes stay quiet for several minutes.
- [ ] **T1.2 Two-camera demo.** Enable `cam2` with a second source + tripwire.
 - *Done when:* both streams show live and alert independently.
- [ ] **T1.3 Animal demo.** Validate that an animal crossing is bucketed `animal` (use a pet, a clip, or a video containing animals).
 - *Done when:* a non-human crossing alerts as `animal`, visibly distinct from `human`.
- [ ] **T1.4 (Optional) Dashboard polish.** Add an event counter by class and click-to-enlarge snapshots. Keep it lightweight.
 - *Done when:* it still launches with one command; no regressions.

## Phase 2 — Motion-gating + slot manager (high-value stretch: the "20 of 300" story)
This is the most on-message feature. Build it if there's time before the demo.
- [ ] **T2.1 Tier-1 motion detector.** Add a cheap motion check (OpenCV background subtraction, e.g. MOG2) per stream that runs *before* the detector.
 - *Done when:* each stream reports a boolean "motion now", with min-blob-size + temporal-persistence filters that ignore minor foliage movement.
- [ ] **T2.2 Slot manager.** Add a manager with a configurable `max_concurrent_slots` (default 20; set it low, e.g. 2–4, for the demo to make the behavior visible). Cameras showing motion request a slot; the detector runs only for cameras holding a slot. Add **perimeter priority** (a per-stream `perimeter: true` flag → always-on, or first in the queue).
 - *Done when:* with more streams than slots, AI runs only on active/priority cameras, the dashboard shows which cameras currently hold a slot, and never more than `max_concurrent_slots` run detection at once.
- [ ] **T2.3 Demonstrate.** Configure ~5–6 streams with 2–3 slots; show AI capacity following activity, with perimeter cameras prioritized.
 - *Done when:* the demo visibly shows "N at a time out of M cameras", matching the proposal narrative.

## Phase 3 — Toward production (after the demo)
- [ ] **T3.1 Event publishing to a Go backend.** Replace/augment the in-process queue: publish events over **MQTT** (or HTTP) using the doc-02 schema. Stand up a minimal **Go** service that consumes and stores them (Postgres).
- [ ] **T3.2 React offline map UI.** Camera pins on a facility layout, draw zones/lines, a live alert feed (WebSocket from Go), and event review with snapshot/clip. Use the doc-02 `IntrusionEvent` TS type.
- [ ] **T3.3 Real RTSP integration.** Pull camera **sub-streams** via ONVIF/RTSP (direct or VideoEdge re-stream); confirm read-only; handle reconnects.
- [ ] **T3.4 Health monitoring + reporting.** Camera/stream health (offline/frozen/black-frame), server/GPU health, and event/incident/health reports.
- [ ] **T3.5 Model fine-tuning.** Fine-tune detection on local species (buffalo, etc.) from site footage; tune the three-stage false-alarm chain against the SLA.
- [ ] **T3.6 HA + performance.** Active-active second L4; TensorRT/FP16/batching/ROI optimizations; event store-and-forward buffering.

## Guardrails
- Never break the **read-only principle** (doc 02).
- Keep `python app.py` a one-command launch through Phase 2.
- Keep the **event schema** stable.
- **Flag the doc-01 open questions** if a task depends on them (e.g., the perimeter-camera count is needed for T2.2 priority).
