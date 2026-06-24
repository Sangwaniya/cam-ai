class Tripwire:
    """
    Virtual tripwire geometry. Checks if an object's track path intersects a defined line segment.
    """
    def __init__(self, p1, p2):
        self.p1 = p1
        self.p2 = p2
        self.crossed_tracks = set()

    def ccw(self, A, B, C):
        """Helper to determine if points A,B,C are listed in counter-clockwise order."""
        return (C[1]-A[1]) * (B[0]-A[0]) > (B[1]-A[1]) * (C[0]-A[0])

    def intersect(self, A, B, C, D):
        """Return True if line segments AB and CD intersect."""
        return self.ccw(A, C, D) != self.ccw(B, C, D) and self.ccw(A, B, C) != self.ccw(A, B, D)

    def get_direction(self, A, B, C, D):
        """Returns a string indicating the direction of crossing across line CD."""
        cross_product = (B[0]-A[0])*(D[1]-C[1]) - (B[1]-A[1])*(D[0]-C[0])
        return "A_to_B" if cross_product > 0 else "B_to_A"

    def update(self, track_id: int, prev_point: tuple, curr_point: tuple):
        """
        Check if a track crossed the tripwire.
        Returns the crossing direction ("A_to_B" or "B_to_A") or None.
        """
        # Debounce: if already crossed, ignore
        if track_id in self.crossed_tracks:
            return None
            
        if self.intersect(prev_point, curr_point, self.p1, self.p2):
            self.crossed_tracks.add(track_id)
            return self.get_direction(prev_point, curr_point, self.p1, self.p2)
            
        return None
