import unittest
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from motion_utils import calculate_motion
except ImportError:
    # This is expected to fail initially in TDD RED phase
    calculate_motion = None

class TestMotionDetection(unittest.TestCase):
    def test_motion_import(self):
        self.assertIsNotNone(calculate_motion, "motion_utils.calculate_motion should exist")

    def test_dynamic_detection(self):
        pos1 = (0.0, 0.0)
        pos2 = (0.5, 0.5)
        # Threshold is 0.1 meters
        is_dynamic = calculate_motion(pos1, pos2, threshold=0.1)
        self.assertTrue(is_dynamic, "Motion of 0.7m should be detected as dynamic")

    def test_static_detection(self):
        pos1 = (0.1, 0.1)
        pos2 = (0.11, 0.11)
        is_dynamic = calculate_motion(pos1, pos2, threshold=0.1)
        self.assertFalse(is_dynamic, "Motion of 0.014m should be detected as static")

if __name__ == "__main__":
    unittest.main()
