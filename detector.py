from ultralytics import YOLO
import numpy as np

class Detector:
    """
    Tier 2 GPU-bound object detector and tracker using YOLOv11 and ByteTrack.
    """
    def __init__(self, stream_id, model_path="yolo11n.pt", classes_of_interest=None, buckets=None):
        self.stream_id = stream_id
        self.model = YOLO(model_path)
        self.classes_of_interest = classes_of_interest or []
        self.buckets = buckets or {}

    def get_bucket(self, class_name):
        """Map fine YOLO classes (e.g. 'person') to buckets (e.g. 'human')"""
        for bucket, classes in self.buckets.items():
            if class_name in classes:
                return bucket
        return "object"

    def detect_and_track(self, frame):
        """
        Runs inference and tracking on a single frame. 
        Returns a list of tracking dictionaries.
        """
        # persist=True maintains ByteTrack history across frames
        results = self.model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False)
        detections = []
        
        if len(results) > 0 and results[0].boxes is not None and results[0].boxes.id is not None:
            result = results[0]
            boxes = result.boxes.xyxy.cpu().numpy()
            track_ids = result.boxes.id.int().cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            cls_ids = result.boxes.cls.int().cpu().numpy()
            
            for box, track_id, conf, cls_id in zip(boxes, track_ids, confs, cls_ids):
                class_name = self.model.names[cls_id]
                
                if class_name in self.classes_of_interest:
                    bucket = self.get_bucket(class_name)
                    # Bottom-center of the bounding box (feet of the person/animal)
                    bottom_center = (int(box[0] + (box[2] - box[0]) / 2), int(box[3]))
                    
                    detections.append({
                        "track_id": track_id,
                        "class_name": class_name,
                        "bucket": bucket,
                        "conf": float(conf),
                        "bbox": box.tolist(),
                        "point": bottom_center
                    })
        return detections
