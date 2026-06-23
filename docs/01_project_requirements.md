# 01 — Project & Requirements

## Background
- A government organization issued a tender (RFP) for an **AI-Enabled Perimeter Intrusion Detection System (PIDS)** for a boundary/perimeter facility in India.
- **We won the bid.** We are now building the system; the immediate deliverable is a **demo** for the client.
- The solution must **augment** the existing CCTV system with AI analytics — **not replace** the cameras, recorders, or VMS.
- The site is a secure government boundary; the system is **on-premises / offline** (no cloud, no internet dependency).

## Existing infrastructure (as-is) — must integrate, must not disrupt
| Component | Detail |
|---|---|
| Cameras | 412 total — majority **TYCO**, ~15 **CP Plus**, ~20–30 **Theia**. ~300 selected for PIDS. |
| NVRs | 18 **TYCO** NVRs (likely American Dynamics **VideoEdge**), 36 TB each. Storage sufficient — **no new storage**. |
| VMS | "**Vector Unified Client**" (almost certainly **victor Unified Client**, American Dynamics / Johnson Controls). Use the RFP's spelling "Vector" in client-facing material. |
| Workstations | 4 operator workstations (8 GB RAM, Xeon E3-1226 v3, **no GPU**) — display/monitoring only; cannot run AI. |

Cameras/NVRs support **ONVIF / RTSP** (standard stream access).

## Functional requirements (from the RFP)
- **AI object detection & classification:** detect and classify **humans** and **animals** — specifically **cat, dog, cow/buffalo, and any animal ≥ dog size**.
- **Virtual boundary / zones:** operators draw **virtual lines, zones, and perimeters** on camera views and define intrusion rules; alert when an object **crosses** a defined boundary.
- **Offline map-based monitoring:** a centralized **offline** map/layout showing **camera locations, direction, and coverage**; alerts surface on the map.
- **Real-time alerts:** **visual and audible** indication.
- **Evidence:** capture **event snapshots and short video clips**.
- **Robustness:** **minimize false alarms** from shadows, lighting changes, **rain, fog, and vegetation movement**; operate **day and night**.
- **Health monitoring:** of **cameras and servers**.
- **Reporting:** generate event / incident / health reports.
- **Integration:** use **existing camera streams**; **no disruption** to existing recording/monitoring; **no additional storage**.
- **Services:** operator **training** and **on-site AI model optimization** (recurring tuning).

## Concurrency requirement (critical — confirmed with the client)
- The AI engine analyzes **20 camera streams concurrently — maximum** at any instant.
- Cameras are **switchable on-demand or automatically**; up to ~**300** cameras are enrolled/selectable.
- This is **NOT** "analyze all 300 at once." The design analyzes **20 at a time** and points those 20 where they matter (see doc 02, two-tier motion-gating).

## Open questions (need human/client confirmation — flag, do NOT guess)
| # | Question | Why it matters |
|---|---|---|
| 1 | How many cameras are on the **actual perimeter line**? | Decides always-on vs. motion-gated allocation. |
| 2 | Is **"20 concurrent"** a hard cap (licensing/spec) or just an estimate of the hardware? | If soft, optimizations allow much wider live coverage. |
| 3 | Which **local animal species** must be reliably detected (buffalo, nilgai, boar…)? | Decides model fine-tuning effort. |
| 4 | Is **high availability** (a redundant server) required? | Adds a second GPU node. |
| 5 | Exact **stream-access method** at the site (direct camera RTSP vs. NVR re-stream)? | Confirmed at site survey; affects integration. |
| 6 | **AMC / support term** duration? | Recurring cost & scope. |

> Commercial note (not relevant to the demo): the RFP's indicative costing table was internally inconsistent — its line items summed to ~₹31 lakh while the stated total was ₹49.9 lakh. Flagged for the commercial track only.
