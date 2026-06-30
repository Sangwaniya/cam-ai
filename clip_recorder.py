import os
from collections import deque
import cv2

# Prefer imageio+ffmpeg for browser-playable H.264 .mp4; fall back to OpenCV mp4v.
try:
    import imageio
    _HAS_IMAGEIO = True
except Exception:
    _HAS_IMAGEIO = False


class ClipRecorder:
    """
    Records a real-time-paced evidence clip around an incident.

      * Continuously buffers the last `prebuffer_secs` of (downscaled) frames.
      * start() opens a writer and flushes the prebuffer (pre-event footage).
      * write() appends frames, throttled to `fps` so playback is wall-clock paced.
      * should_stop() is true once activity goes quiet (`linger_secs`) or `max_secs`.

    Writes H.264 .mp4 via imageio/ffmpeg when available (plays in browsers),
    else OpenCV mp4v. If neither works, recording is skipped gracefully and the
    incident is still logged with its snapshot + timestamps (clip = None).
    """
    def __init__(self, stream_id, out_dir="clips", max_width=640,
                 prebuffer_secs=3.0, max_secs=20.0, linger_secs=2.0, fps=15):
        self.stream_id = stream_id
        self.out_dir = out_dir
        self.max_width = max_width
        self.prebuffer_secs = prebuffer_secs
        self.max_secs = max_secs
        self.linger_secs = linger_secs
        self.fps = max(1, int(fps))
        os.makedirs(out_dir, exist_ok=True)

        self._buffer = deque()          # (ts, frame_bgr_small)
        self._last_buf_ts = 0.0
        self._recording = False
        self._writer = None
        self._backend = None            # "imageio" | "cv2"
        self._url = None
        self._path = None
        self._started_at = None
        self._last_write_ts = 0.0
        self._last_activity_ts = 0.0

    def _resize(self, frame):
        h, w = frame.shape[:2]
        if w <= self.max_width:
            return frame
        scale = self.max_width / float(w)
        return cv2.resize(frame, (self.max_width, int(h * scale)))

    def is_recording(self):
        return self._recording

    def buffer_frame(self, now, frame):
        """Maintain a rolling pre-event buffer, sampled at `fps`."""
        if now - self._last_buf_ts < 1.0 / self.fps:
            return
        self._last_buf_ts = now
        self._buffer.append((now, self._resize(frame).copy()))
        cutoff = now - self.prebuffer_secs
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

    def _open(self, sample, clip_id):
        h, w = sample.shape[:2]
        path = os.path.join(self.out_dir, f"{clip_id}.mp4")
        if _HAS_IMAGEIO:
            try:
                self._writer = imageio.get_writer(
                    path, fps=self.fps, codec="libx264", quality=8,
                    macro_block_size=None, ffmpeg_log_level="error",
                )
                self._backend = "imageio"
                self._path, self._url = path, f"/clips/{clip_id}.mp4"
                return True
            except Exception as e:
                print(f"[clip:{self.stream_id}] imageio writer failed ({e}); trying OpenCV")
        try:
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
            if not writer.isOpened():
                raise RuntimeError("VideoWriter not opened")
            self._writer = writer
            self._backend = "cv2"
            self._path, self._url = path, f"/clips/{clip_id}.mp4"
            return True
        except Exception as e:
            print(f"[clip:{self.stream_id}] clip recording unavailable ({e})")
            self._writer = None
            return False

    def _write_frame(self, frame):
        small = self._resize(frame)
        if self._backend == "imageio":
            self._writer.append_data(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        elif self._backend == "cv2":
            self._writer.write(small)

    def start(self, now, clip_id, frame):
        if self._recording:
            return
        if not self._open(self._resize(frame), clip_id):
            return
        self._recording = True
        self._started_at = self._buffer[0][0] if self._buffer else now
        self._last_activity_ts = now
        for _, f in list(self._buffer):    # flush pre-event footage
            self._write_frame(f)
        self._last_write_ts = now

    def write(self, now, frame, active=False):
        if not self._recording:
            return
        if active:
            self._last_activity_ts = now
        if now - self._last_write_ts >= 1.0 / self.fps:
            self._last_write_ts = now
            self._write_frame(frame)

    def should_stop(self, now):
        if not self._recording:
            return False
        return (now - self._last_activity_ts > self.linger_secs) or \
               (now - self._started_at > self.max_secs)

    def finalize(self, now):
        """Close the writer; return (clip_url_or_None, started_at, ended_at)."""
        url, started = self._url, self._started_at
        if self._writer is not None:
            try:
                self._writer.close() if self._backend == "imageio" else self._writer.release()
            except Exception:
                pass
        self._writer = None
        self._recording = False
        self._backend = None
        self._url = None
        self._path = None
        self._started_at = None
        return url, started, now
