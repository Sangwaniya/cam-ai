import cv2
import numpy as np

class MotionDetector:
    """
    Tier 1 CPU-bound motion detector using Background Subtraction.
    Should be run on a downscaled or sub-stream frame to save CPU.
    """
    def __init__(self, threshold=500, history=500, varThreshold=16):
        self.threshold = threshold
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=history, varThreshold=varThreshold, detectShadows=True)
        # Morphological kernel to remove small noise (e.g. leaves)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def check_motion(self, frame, roi_pixels=None):
        """
        Takes a BGR frame and an optional ROI polygon.
        Returns (has_motion: bool, fg_mask: np.ndarray, boxes: list)
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fg_mask = self.bg_subtractor.apply(gray)
        
        # Strictly enforce the ROI Boundary
        if roi_pixels is not None and len(roi_pixels) > 2:
            roi_mask = np.zeros_like(fg_mask)
            pts = np.array(roi_pixels, dtype=np.int32)
            cv2.fillPoly(roi_mask, [pts], 255)
            fg_mask = cv2.bitwise_and(fg_mask, roi_mask)
            
        _, fg_mask = cv2.threshold(fg_mask, 254, 255, cv2.THRESH_BINARY)
        
        # Morphological open to remove noise
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self.kernel)
        
        # Find contours
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        has_motion = False
        boxes = []
        for contour in contours:
            if cv2.contourArea(contour) > self.threshold:
                has_motion = True
                x, y, w, h = cv2.boundingRect(contour)
                boxes.append((x, y, w, h))
                
        return has_motion, fg_mask, boxes
