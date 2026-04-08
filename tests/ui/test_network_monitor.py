import unittest

from PyQt6.QtCore import QPoint, QRect, QSize

from src.ui.network_monitor import NetworkMonitorWidget


class TestNetworkMonitorWidget(unittest.TestCase):
    def test_clamp_point_to_rect_moves_offscreen_position_back_inside_bounds(self):
        clamped = NetworkMonitorWidget._clamp_point_to_rect(
            QPoint(5000, 4000),
            QSize(140, 48),
            QRect(0, 0, 1920, 1040),
        )

        self.assertEqual(clamped, QPoint(1780, 992))

    def test_clamp_point_to_rect_preserves_position_when_already_visible(self):
        clamped = NetworkMonitorWidget._clamp_point_to_rect(
            QPoint(120, 80),
            QSize(140, 48),
            QRect(0, 0, 1920, 1040),
        )

        self.assertEqual(clamped, QPoint(120, 80))

    def test_clamp_point_to_rect_preserves_position_in_taskbar_band(self):
        clamped = NetworkMonitorWidget._clamp_point_to_rect(
            QPoint(120, 1005),
            QSize(140, 48),
            QRect(0, 0, 1920, 1080),
        )

        self.assertEqual(clamped, QPoint(120, 1005))


if __name__ == "__main__":
    unittest.main()
