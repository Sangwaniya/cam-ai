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

# Setup intrusion logger
os.makedirs('logs', exist_ok=True)
intrusion_logger = logging.getLogger('intrusions')
intrusion_logger.setLevel(logging.INFO)
_fh = logging.FileHandler('logs/intrusions.log')
_fh.setFormatter(logging.Formatter('%(message)s'))
intrusion_logger.addHandler(_fh)

class Pipeline(threading.Thread):
    """
    Per-stream worker thread orchestrating the Tier-1 to Tier-2 handoff.
    """
    def __init__(self, stream_id, config, scheduler, event_queue):
        super().__init__()
        self.stream_id = stream_id
        self.config = config
        self.scheduler = scheduler
        self.event_queue = event_queue
        
        # Load stream config
        self.stream_config = config['streams'][stream_id]
        self.source = self.stream_config['source']
        if str(self.source).isdigit():
            self.source = int(self.source)
            
        self.tripwire_coords = self.stream_config['tripwire']
        self.tripwire = Tripwire(tuple(self.tripwire_coords[0]), tuple(self.tripwire_coords[1]))
        self.roi_percents = self.stream_config.get('roi', None)
        
        # Core engines
        self.detector = Detector(
            stream_id, 
            classes_of_interest=config.get('classes_of_interest', []),
            buckets=config.get('buckets', {})
        )
        self.motion = MotionDetector(threshold=config.get('system', {}).get('motion_threshold', 500))
        
        self.running = True
        self.latest_frame = None
        self.track_history = {} # track_id -> list of historic points
        self.alerted_ids = set()  # track_ids that already triggered an ROI intrusion alert
        self.show_motion = True   # Toggle for split-screen motion view
        
    def run(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"❌ ERROR: Failed to open video source '{self.source}' for stream '{self.stream_id}'")
            self.running = False
            return
            
        frame_count = 0
        motion_fps = self.config.get('system', {}).get('motion_fps', 5)
        motion_skip = max(1, 30 // motion_fps)
        has_motion = False
        motion_mask = None
        motion_boxes = []
        
        while self.running:
            ret, frame = cap.read()
            if not ret:
                # Loop video for the demo
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
                
            frame_count += 1
            
            # 1. Tier 1: CPU Motion Check
            roi_pixels = None
            if self.roi_percents:
                orig_h, orig_w = frame.shape[:2]
                roi_pixels = [[int(x * orig_w), int(y * orig_h)] for x, y in self.roi_percents]
                
            if frame_count % motion_skip == 0:
                has_motion, motion_mask, motion_boxes = self.motion.check_motion(frame, roi_pixels)
                
            # Render Left Pane (Motion Mask)
            if motion_mask is None:
                motion_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            left_pane = cv2.cvtColor(motion_mask, cv2.COLOR_GRAY2BGR)
            for (x, y, w, h) in motion_boxes:
                cv2.rectangle(left_pane, (x, y), (x+w, y+h), (255, 0, 0), 2)
                cv2.putText(left_pane, "Motion Blob", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            
            status_color = (0, 0, 255) if has_motion else (0, 255, 0)
            status_text = "Tier-1 Motion: ACTIVE" if has_motion else "Tier-1 Motion: IDLE"
            cv2.putText(left_pane, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
            
            # Render Right Pane (YOLO + Tripwire)
            right_pane = frame.copy()
            
            if roi_pixels:
                pts = np.array(roi_pixels, np.int32).reshape((-1, 1, 2))
                cv2.polylines(left_pane, [pts], isClosed=True, color=(0, 255, 255), thickness=2)
                cv2.polylines(right_pane, [pts], isClosed=True, color=(0, 255, 255), thickness=2)
                cv2.putText(right_pane, "ROI Boundary", (pts[0][0][0], pts[0][0][1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            
            # 2. Tier 2: Request GPU Slot if motion is detected
            if has_motion:
                cv2.putText(right_pane, "Tier-2 GPU: SCANNING", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                priority = self.stream_config.get('priority', 0)
                if self.scheduler.acquire_slot(self.stream_id, priority=priority):
                    try:
                        detections = self.detector.detect_and_track(frame)

                        # Filter detections to ROI boundary
                        if roi_pixels is not None and len(roi_pixels) > 2:
                            roi_contour = np.array(roi_pixels, dtype=np.int32)
                            detections = [d for d in detections if cv2.pointPolygonTest(roi_contour, tuple(d['point']), False) >= 0]
                        
                        # 3. Fire intrusion events
                        for d in detections:
                            tid = d['track_id']
                            point = d['point']
                            
                            fired = False
                            
                            # ROI mode: any NEW detection inside ROI = intrusion
                            if roi_pixels is not None and len(roi_pixels) > 2:
                                if tid not in self.alerted_ids:
                                    self.alerted_ids.add(tid)
                                    event = {
                                        "stream_id": self.stream_id,
                                        "stream_name": self.stream_config.get('name', self.stream_id),
                                        "class": d['class_name'],
                                        "bucket": d['bucket'],
                                        "direction": "roi_breach",
                                        "conf": d['conf'],
                                        "ts": time.time(),
                                    }
                                    ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    intrusion_logger.info(
                                        f"[{ts_str}] INTRUSION | stream={self.stream_id} | "
                                        f"name={self.stream_config.get('name', self.stream_id)} | "
                                        f"bucket={d['bucket']} | class={d['class_name']} | "
                                        f"direction=roi_breach | confidence={d['conf']:.3f} | "
                                        f"track_id={tid}"
                                    )
                                    self.event_queue.put((event, frame.copy()))
                                    fired = True
                            else:
                                # Fallback: tripwire crossing mode (when no ROI is set)
                                if tid in self.track_history:
                                    prev_point = self.track_history[tid][-1]
                                    direction = self.tripwire.update(tid, prev_point, point)
                                    if direction:
                                        event = {
                                            "stream_id": self.stream_id,
                                            "stream_name": self.stream_config.get('name', self.stream_id),
                                            "class": d['class_name'],
                                            "bucket": d['bucket'],
                                            "direction": direction,
                                            "conf": d['conf'],
                                            "ts": time.time(),
                                        }
                                        ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                        intrusion_logger.info(
                                            f"[{ts_str}] INTRUSION | stream={self.stream_id} | "
                                            f"name={self.stream_config.get('name', self.stream_id)} | "
                                            f"bucket={d['bucket']} | class={d['class_name']} | "
                                            f"direction={direction} | confidence={d['conf']:.3f} | "
                                            f"track_id={tid}"
                                        )
                                        self.event_queue.put((event, frame.copy()))
                                        fired = True
                            
                            # Maintain track history
                            if tid not in self.track_history:
                                self.track_history[tid] = []
                            self.track_history[tid].append(point)
                            if len(self.track_history[tid]) > 30:
                                self.track_history[tid].pop(0)
                                
                        # Annotate right pane with AI detections
                        for d in detections:
                            box = d['bbox']
                            color = (0, 165, 255) if d['bucket'] == 'animal' else (0, 255, 0)
                            cv2.rectangle(right_pane, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), color, 2)
                            cv2.putText(right_pane, f"{d['bucket']}:{d['class_name']}", (int(box[0]), int(box[1])-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                            
                    finally:
                        self.scheduler.release_slot(self.stream_id)
            else:
                cv2.putText(right_pane, "Tier-2 GPU: IDLE (Sleeping)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
            
            
            # Combine into final output frame
            if self.show_motion:
                combined_frame = np.hstack((left_pane, right_pane))
            else:
                combined_frame = right_pane
            
            # Encode frame for MJPEG streaming
            _, buffer = cv2.imencode('.jpg', combined_frame)
            self.latest_frame = buffer.tobytes()
            
            # Small sleep to yield CPU
            time.sleep(0.01)
            
        cap.release()

    def update_roi(self, roi_percents):
        """Update ROI at runtime from the API"""
        self.roi_percents = roi_percents

    def set_show_motion(self, show):
        """Toggle the split-screen motion view"""
        self.show_motion = show

    def stop(self):
        self.running = False
