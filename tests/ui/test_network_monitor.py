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

    def test_infer_taskbar_rect_detects_bottom_taskbar_from_available_geometry(self):
        taskbar_rect = NetworkMonitorWidget._infer_taskbar_rect(
            QRect(0, 0, 1920, 1080),
            QRect(0, 0, 1920, 1040),
        )

        self.assertEqual(taskbar_rect, QRect(0, 1040, 1920, 40))

    def test_infer_taskbar_rect_detects_left_taskbar_from_available_geometry(self):
        taskbar_rect = NetworkMonitorWidget._infer_taskbar_rect(
            QRect(0, 0, 1920, 1080),
            QRect(80, 0, 1840, 1080),
        )

        self.assertEqual(taskbar_rect, QRect(0, 0, 80, 1080))

    def test_infer_taskbar_rect_falls_back_to_bottom_band_when_no_band_exists(self):
        taskbar_rect = NetworkMonitorWidget._infer_taskbar_rect(
            QRect(0, 0, 1920, 1080),
            QRect(0, 0, 1920, 1080),
        )

        self.assertEqual(taskbar_rect, QRect(0, 1032, 1920, 48))

    def test_taskbar_left_anchor_point_uses_left_edge_of_horizontal_taskbar(self):
        anchored = NetworkMonitorWidget._taskbar_left_anchor_point(
            QRect(0, 1040, 1920, 40),
            QSize(120, 32),
        )

        self.assertEqual(anchored, QPoint(6, 1044))

    def test_taskbar_left_anchor_point_keeps_tall_widget_inside_screen(self):
        anchored = NetworkMonitorWidget._taskbar_left_anchor_point(
            QRect(0, 1040, 1920, 40),
            QSize(120, 56),
            bounding_rect=QRect(0, 0, 1920, 1080),
        )

        self.assertEqual(anchored, QPoint(6, 1024))

    def test_taskbar_left_anchor_point_uses_top_edge_of_vertical_taskbar(self):
        anchored = NetworkMonitorWidget._taskbar_left_anchor_point(
            QRect(0, 0, 80, 1080),
            QSize(120, 32),
        )

        self.assertEqual(anchored, QPoint(0, 6))


if __name__ == "__main__":
    unittest.main()
