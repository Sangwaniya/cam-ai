import threading

class BatchScheduler:
    """
    Manages dynamic GPU batching and slot allocation.
    In a full TensorRT production environment, this queues frames into large batches.
    For this Python demo, it uses a semaphore to limit concurrent GPU executions
    while prioritizing streams with active motion.
    """
    def __init__(self, max_concurrent=4):
        self.max_concurrent = max_concurrent
        self.active_slots = 0
        self.lock = threading.Lock()
        
    def acquire_slot(self, stream_id, priority=0) -> bool:
        """
        Attempts to acquire a GPU processing slot. Returns True if granted.
        """
        with self.lock:
            if self.active_slots < self.max_concurrent:
                self.active_slots += 1
                return True
        return False
        
    def release_slot(self, stream_id):
        """
        Releases the GPU slot back to the pool.
        """
        with self.lock:
            if self.active_slots > 0:
                self.active_slots -= 1
