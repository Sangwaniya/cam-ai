import cv2
import time
import logging
import os
import threading
import numpy as np
from datetime import datetime
from detector import Detector
from tripwire import Tripwire
from motion import MotionDetector
from clip_recorder import ClipRecorder

# Setup intrusion logger
os.makedirs('logs', exist_ok=True)
intrusion_logger = logging.getLogger('intrusions')
intrusion_logger.setLevel(logging.INFO)
if not intrusion_logger.handlers:
    _fh = logging.FileHandler('logs/intrusions.log')
    _fh.setFormatter(logging.Formatter('%(message)s'))
    intrusion_logger.addHandler(_fh)

SNAPSHOT_DIR = 'snapshots'
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

BUCKET_COLORS = {"human": (0, 0, 255), "animal": (0, 165, 255), "object": (255, 100, 0)}


class Pipeline(threading.Thread):
    """
    Per-stream worker thread: Tier-1 motion gate -> Tier-2 GPU scan ->
    tripwire/ROI events -> live alerts + recorded incident clips.
    """
    def __init__(self, stream_id, config, scheduler, event_queue):
        super().__init__()
        self.stream_id = stream_id
        self.config = config
        self.scheduler = scheduler
        self.event_queue = event_queue

        self.stream_config = config['streams'][stream_id]
        self.source = self.stream_config['source']
        if str(self.source).isdigit():
            self.source = int(self.source)

        self.tripwire_coords = self.stream_config['tripwire']
        self.priority = self.stream_config.get('priority', 0)

        sys_cfg = config.get('system', {})
        self.alert_cooldown = sys_cfg.get('alert_cooldown', 3.0)
        self.tripwire = Tripwire(tuple(self.tripwire_coords[0]), tuple(self.tripwire_coords[1]),
                                 cooldown=self.alert_cooldown)
        self.roi_percents = self.stream_config.get('roi', None)

        self.detector = Detector(
            stream_id,
            classes_of_interest=config.get('classes_of_interest', []),
            buckets=config.get('buckets', {}),
            conf=sys_cfg.get('conf', 0.35),
        )
        self.motion = MotionDetector(threshold=sys_cfg.get('motion_threshold', 500))

        clip_cfg = config.get('clips', {})
        self.clips_enabled = clip_cfg.get('enabled', True)
        self.recorder = ClipRecorder(
            stream_id, out_dir='clips',
            max_width=clip_cfg.get('max_width', 640),
            prebuffer_secs=clip_cfg.get('prebuffer_secs', 3),
            max_secs=clip_cfg.get('max_secs', 20),
            linger_secs=clip_cfg.get('linger_secs', 2),
            fps=clip_cfg.get('fps', 15),
        )

        self.running = True
        self.latest_frame = None
        self.track_history = {}
        self.first_seen = {}     # track_id -> first time seen
        self.last_seen = {}      # track_id -> last time seen
        self.roi_last_fire = {}
        self.show_motion = True

        # Active incident being recorded
        self.incident = None
        self.incident_tids = set()

        # Health / metrics
        self.opened = False
        self.last_frame_ts = 0.0
        self.fps_ema = 0.0
        self.current_motion = False
        self.current_scanning = False
        self.current_objects = 0

    # ---------- snapshots / events ----------
    def _save_snapshot(self, frame, d, ts):
        img = frame.copy()
        box = d['bbox']
        color = BUCKET_COLORS.get(d['bucket'], (255, 255, 255))
        cv2.rectangle(img, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), color, 3)
        cv2.putText(img, f"{d['bucket']}:{d['class_name']} {d['conf'] * 100:.0f}%",
                    (int(box[0]), max(20, int(box[1]) - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        fname = f"{self.stream_id}_{int(ts * 1000)}.jpg"
        cv2.imwrite(os.path.join(SNAPSHOT_DIR, fname), img)
        return f"/snapshots/{fname}"

    def _emit_alert(self, d, direction, snapshot_url, ts, ts_start):
        event = {
            "type": "alert",
            "stream_id": self.stream_id,
            "stream_name": self.stream_config.get('name', self.stream_id),
            "class": d['class_name'], "bucket": d['bucket'], "direction": direction,
            "conf": d['conf'], "ts": ts, "ts_start": ts_start, "snapshot": snapshot_url,
        }
        ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        intrusion_logger.info(
            f"[{ts_str}] INTRUSION | stream={self.stream_id} | "
            f"name={self.stream_config.get('name', self.stream_id)} | "
            f"bucket={d['bucket']} | class={d['class_name']} | "
            f"direction={direction} | confidence={d['conf']:.3f} | track_id={d['track_id']}"
        )
        self.event_queue.put(event)

    def _trigger(self, d, direction, frame, now):
        tid = d['track_id']
        ts_start = self.first_seen.get(tid, now)
        snapshot_url = self._save_snapshot(frame, d, now)
        self._emit_alert(d, direction, snapshot_url, now, ts_start)

        if not self.clips_enabled:
            return
        if self.incident is None:
            clip_id = f"{self.stream_id}_{int(now * 1000)}"
            self.recorder.start(now, clip_id, frame)
            self.incident = {
                "id": clip_id, "stream_id": self.stream_id,
                "stream_name": self.stream_config.get('name', self.stream_id),
                "snapshot": snapshot_url, "objects": [],
            }
            self.incident_tids = set()
        self.incident["objects"].append({
            "bucket": d['bucket'], "class": d['class_name'], "direction": direction,
            "conf": round(d['conf'], 3), "ts": now, "track_id": tid,
        })
        self.incident_tids.add(tid)

    def _finalize_incident(self, now):
        clip_url, started, ended = self.recorder.finalize(now)
        inc = self.incident
        starts = [self.first_seen.get(t) for t in self.incident_tids if self.first_seen.get(t)]
        ends = [self.last_seen.get(t) for t in self.incident_tids if self.last_seen.get(t)]
        inc["ts_start"] = min(starts) if starts else (started or now)
        inc["ts_end"] = max(ends) if ends else ended
        inc["duration"] = round(max(0.0, inc["ts_end"] - inc["ts_start"]), 1)
        inc["clip"] = clip_url
        inc["type"] = "incident"
        self.event_queue.put(inc)
        self.incident = None
        self.incident_tids = set()

    def _cleanup_tracks(self, now):
        stale = [tid for tid, t in self.last_seen.items() if now - t > 30]
        for tid in stale:
            self.last_seen.pop(tid, None)
            self.first_seen.pop(tid, None)
            self.track_history.pop(tid, None)
            self.roi_last_fire.pop(tid, None)
        self.tripwire.cleanup(set(self.last_seen.keys()), now)

    def health(self, now=None):
        now = time.time() if now is None else now
        return {
            "online": self.opened and (now - self.last_frame_ts) < 5.0,
            "fps": round(self.fps_ema, 1),
            "motion": self.current_motion,
            "scanning": self.current_scanning,
            "objects": self.current_objects,
            "priority": self.priority,
            "recording": self.recorder.is_recording(),
        }

    # ---------- main loop ----------
    def run(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"❌ ERROR: Failed to open video source '{self.source}' for stream '{self.stream_id}'")
            self.running = False
            return
        self.opened = True

        frame_count = 0
        sys_cfg = self.config.get('system', {})
        motion_fps = sys_cfg.get('motion_fps', 5)
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
        motion_skip = max(1, int(round(src_fps / motion_fps)))
        has_motion, motion_mask, motion_boxes = False, None, []

        while self.running:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            frame_count += 1
            now = time.time()
            if self.last_frame_ts:
                dt = now - self.last_frame_ts
                if dt > 0:
                    inst = 1.0 / dt
                    self.fps_ema = inst if self.fps_ema == 0 else (0.9 * self.fps_ema + 0.1 * inst)
            self.last_frame_ts = now

            if self.clips_enabled:
                self.recorder.buffer_frame(now, frame)

            roi_pixels = None
            if self.roi_percents:
                oh, ow = frame.shape[:2]
                roi_pixels = [[int(x * ow), int(y * oh)] for x, y in self.roi_percents]

            if frame_count % motion_skip == 0:
                has_motion, motion_mask, motion_boxes = self.motion.check_motion(frame, roi_pixels)
            self.current_motion = has_motion

            # ----- left pane (motion) -----
            if motion_mask is None:
                motion_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            left_pane = cv2.cvtColor(motion_mask, cv2.COLOR_GRAY2BGR)
            for (x, y, w, h) in motion_boxes:
                cv2.rectangle(left_pane, (x, y), (x + w, y + h), (255, 0, 0), 2)
                cv2.putText(left_pane, "Motion Blob", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            sc = (0, 0, 255) if has_motion else (0, 255, 0)
            cv2.putText(left_pane, "Tier-1 Motion: ACTIVE" if has_motion else "Tier-1 Motion: IDLE",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, sc, 2)

            # ----- right pane (AI) -----
            right_pane = frame.copy()
            if roi_pixels:
                pts = np.array(roi_pixels, np.int32).reshape((-1, 1, 2))
                cv2.polylines(left_pane, [pts], True, (0, 255, 255), 2)
                cv2.polylines(right_pane, [pts], True, (0, 255, 255), 2)
                cv2.putText(right_pane, "ROI Boundary", (pts[0][0][0], pts[0][0][1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            else:
                cv2.line(right_pane, tuple(self.tripwire_coords[0]), tuple(self.tripwire_coords[1]),
                         (0, 255, 255), 2)

            scanning, detections = False, []
            if has_motion:
                if self.scheduler.request(self.stream_id, self.priority):
                    scanning = True
                    cv2.putText(right_pane, "Tier-2 GPU: SCANNING", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    detections = self.detector.detect_and_track(frame)
                    if roi_pixels is not None and len(roi_pixels) > 2:
                        rc = np.array(roi_pixels, dtype=np.int32)
                        detections = [d for d in detections
                                      if cv2.pointPolygonTest(rc, tuple(d['point']), False) >= 0]
                    for d in detections:
                        tid, point = d['track_id'], d['point']
                        self.first_seen.setdefault(tid, now)
                        self.last_seen[tid] = now
                        if roi_pixels is not None and len(roi_pixels) > 2:
                            if now - self.roi_last_fire.get(tid, 0.0) >= self.alert_cooldown:
                                self.roi_last_fire[tid] = now
                                self._trigger(d, "roi_breach", frame, now)
                        else:
                            if self.track_history.get(tid):
                                direction = self.tripwire.update(tid, self.track_history[tid][-1], point, now)
                                if direction:
                                    self._trigger(d, direction, frame, now)
                        self.track_history.setdefault(tid, []).append(point)
                        if len(self.track_history[tid]) > 30:
                            self.track_history[tid].pop(0)
                    for d in detections:
                        box = d['bbox']
                        color = BUCKET_COLORS.get(d['bucket'], (0, 255, 0))
                        cv2.rectangle(right_pane, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), color, 2)
                        cv2.putText(right_pane, f"{d['bucket']}:{d['class_name']}",
                                    (int(box[0]), int(box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                else:
                    cv2.putText(right_pane, "Tier-2 GPU: WAITING (slot busy)", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            else:
                cv2.putText(right_pane, "Tier-2 GPU: IDLE (Sleeping)", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
            self.current_scanning = scanning
            self.current_objects = len(detections)

            # ----- incident clip lifecycle -----
            if self.clips_enabled and self.recorder.is_recording():
                seen_now = {d['track_id'] for d in detections}
                self.recorder.write(now, frame, active=bool(self.incident_tids & seen_now))
                if self.recorder.should_stop(now):
                    self._finalize_incident(now)
                else:
                    cv2.circle(right_pane, (right_pane.shape[1] - 28, 28), 8, (0, 0, 255), -1)
                    cv2.putText(right_pane, "REC", (right_pane.shape[1] - 72, 34),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            if frame_count % 300 == 0:
                self._cleanup_tracks(now)

            combined = np.hstack((left_pane, right_pane)) if self.show_motion else right_pane
            _, buf = cv2.imencode('.jpg', combined)
            self.latest_frame = buf.tobytes()
            time.sleep(0.01)

        if self.clips_enabled and self.recorder.is_recording():
            self._finalize_incident(time.time())
        cap.release()

    def update_roi(self, roi_percents):
        self.roi_percents = roi_percents

    def set_show_motion(self, show):
        self.show_motion = show

    def stop(self):
        self.running = False
