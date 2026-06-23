# 03 — Demo Specification

## Purpose
A **working local demo** to present to the client, proving the core PIDS analytics work on their kind of footage.

## In scope (must work)
- Ingest **1–2 video streams** (file, RTSP, or webcam).
- Real-time **detection + classification** with on-screen boxes/labels (human / animal / object).
- A **virtual tripwire** per stream; **alert fires on crossing**.
- **Visual alert** (line flashes red, INTRUSION banner, alert feed) + **audible alert** (beep).
- **Snapshot evidence** per alert, shown in the feed.
- **Multi-camera** view (a second stream).
- Runs **locally** with one command; GPU optional.

## Out of scope for the demo (deferred to production)
- Tier-1 **motion-gating** and the **slot manager** (the 20-of-300 logic). **Optional stretch** — see the task list; it's the most on-message feature if time allows.
- **High availability**, **Vector/VMS integration**, **real RTSP at scale**.
- The production **Go backend** and **React map UI** (the demo uses the built-in FastAPI/HTML dashboard).
- **Health monitoring**, **reporting**, **video clips**, **model fine-tuning** — nice-to-haves, not required for the demo.

## Acceptance criteria (the demo is "done" when)
1. `pip install -r requirements.txt` then `python app.py` starts with no errors.
2. Opening `http://localhost:8000` shows live annotated video for each configured stream.
3. A person walking across the tripwire produces, within ~1–2 s: a box labeled `person/human`, the line flashing red, an INTRUSION banner, a new alert in the feed with a snapshot, and an audible beep.
4. An animal (or a stand-in clip) crossing is classified in the `animal` bucket and alerts distinctly from a human.
5. A second stream works simultaneously.
6. The tripwire position matches the boundary in the demo footage.
7. No crashes over a multi-minute continuous run (looping video).

## Demo script (for the presentation)
1. Show live detection with labels on the perimeter footage.
2. A **person crosses** → instant visual + audible alert + snapshot.
3. An **animal crosses** → classified differently (shows the human/animal bifurcation).
4. Show the **second camera**.
5. Explain (using the technical proposal): ~1–2 s response, 20-concurrent with headroom, motion-gating for the full 300, and no disruption to the existing system.

## Demo assets to obtain
- **Best:** a 30–60 s clip from the client's **actual perimeter cameras** (ask the contact). Tune the tripwire + thresholds to it.
- **Fallback:** webcam (`source: "0"`) or a perimeter / CCTV-style sample video.

## Demo hardware
- Laptop with an **NVIDIA GPU** is ideal; **CPU works for one stream** (lower `imgsz`, raise `process_every_n_frames`).
- If the **L4 server** is already procured, demo on it — it's the real target.
