import math

def calculate_motion(pos1, pos2, threshold=0.1):
    """
    Calculates Euclidean distance between two positions.
    Returns True if distance > threshold (Dynamic), False otherwise (Static).
    """
    if pos1 is None or pos2 is None:
        return False
    
    x1, y1 = pos1
    x2, y2 = pos2
    
    distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    return distance > threshold
