import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from src.ui.screenshot_overlay import ScreenshotOverlay


_APP = QApplication.instance() or QApplication([])


class TestScreenshotOverlay(unittest.TestCase):
    def setUp(self):
        self.overlay = ScreenshotOverlay()

    def tearDown(self):
        self.overlay.close()

    def test_find_movable_action_index_hits_rect_line_and_text(self):
        self.overlay.draw_actions = [
            {
                "type": "rect",
                "color": QColor("#FF3333"),
                "points": [QPoint(20, 20), QPoint(90, 80)],
                "thickness": 3,
            },
            {
                "type": "line",
                "color": QColor("#3399FF"),
                "points": [QPoint(120, 40), QPoint(200, 40)],
                "thickness": 4,
            },
            {
                "type": "text",
                "color": QColor("#33CC33"),
                "text": "Hello",
                "pos": QPoint(220, 30),
                "font_size": 18,
            },
        ]

        self.assertEqual(self.overlay._find_movable_action_index(QPoint(30, 30)), 0)
        self.assertEqual(self.overlay._find_movable_action_index(QPoint(160, 40)), 1)
        self.assertEqual(self.overlay._find_movable_action_index(QPoint(224, 36)), 2)

    def test_translate_action_moves_line_and_text(self):
        line_action = {
            "type": "line",
            "points": [QPoint(10, 10), QPoint(30, 20)],
            "thickness": 3,
        }
        text_action = {"type": "text", "pos": QPoint(40, 50), "text": "A"}
        number_action = {"type": "number", "pos": QPoint(80, 90), "number": 1}

        ScreenshotOverlay._translate_action(line_action, QPoint(5, -3))
        ScreenshotOverlay._translate_action(text_action, QPoint(-2, 4))
        ScreenshotOverlay._translate_action(number_action, QPoint(10, -20))

        self.assertEqual(line_action["points"], [QPoint(15, 7), QPoint(35, 17)])
        self.assertEqual(text_action["pos"], QPoint(38, 54))
        self.assertEqual(number_action["pos"], QPoint(90, 70))

    def test_number_text_color_contrasts_with_marker_background(self):
        self.assertEqual(
            ScreenshotOverlay._number_text_color(QColor("#FF3333")).name().upper(),
            "#FFFFFF",
        )
        self.assertEqual(
            ScreenshotOverlay._number_text_color(QColor("#3399FF")).name().upper(),
            "#FFFFFF",
        )
        self.assertEqual(
            ScreenshotOverlay._number_text_color(QColor("#FFCC00")).name().upper(),
            "#000000",
        )
        self.assertEqual(
            ScreenshotOverlay._number_text_color(QColor("#FFFFFF")).name().upper(),
            "#000000",
        )
        self.assertEqual(
            ScreenshotOverlay._number_text_color(QColor("#000000")).name().upper(),
            "#FFFFFF",
        )

    def test_number_tool_adds_incrementing_movable_markers(self):
        self.overlay.selection_rect = QRect(0, 0, 300, 200)
        self.overlay.draw_mode = "number"

        first_press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(50, 60),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        second_press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(120, 90),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.overlay.mousePressEvent(first_press)
        self.overlay.mousePressEvent(second_press)

        self.assertEqual([a["number"] for a in self.overlay.draw_actions], [1, 2])
        self.assertEqual(self.overlay._find_movable_action_index(QPoint(50, 60)), 0)
        self.assertEqual(self.overlay._find_movable_action_index(QPoint(120, 90)), 1)

    def test_left_click_outside_selection_with_annotations_keeps_selection(self):
        self.overlay.selection_rect = QRect(20, 20, 120, 90)
        original_rect = QRect(self.overlay.selection_rect)
        self.overlay.draw_actions = [
            {
                "type": "number",
                "color": QColor("#FF3333"),
                "number": 1,
                "pos": QPoint(60, 60),
                "size": 26,
                "thickness": 3,
            }
        ]

        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(220, 180),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.overlay.mousePressEvent(press_event)

        self.assertEqual(self.overlay.selection_rect, original_rect)
        self.assertEqual(len(self.overlay.draw_actions), 1)
        self.assertFalse(self.overlay.is_drawing)

    def test_direct_drag_existing_annotation_even_when_draw_tool_is_active(self):
        self.overlay.selection_rect = QRect(0, 0, 300, 200)
        self.overlay.draw_mode = "rect"
        self.overlay.draw_actions = [
            {
                "type": "line",
                "color": QColor("#3399FF"),
                "points": [QPoint(40, 40), QPoint(120, 40)],
                "thickness": 4,
            }
        ]

        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(80, 40),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(100, 55),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release_event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(100, 55),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.overlay.mousePressEvent(press_event)
        self.assertTrue(self.overlay.is_moving_action)
        self.assertIsNone(self.overlay.current_action)

        self.overlay.mouseMoveEvent(move_event)
        self.overlay.mouseReleaseEvent(release_event)

        self.assertEqual(
            self.overlay.draw_actions[0]["points"], [QPoint(60, 55), QPoint(140, 55)]
        )

    def test_text_tool_prefers_dragging_existing_text_over_creating_new_text(self):
        self.overlay.selection_rect = QRect(0, 0, 300, 200)
        self.overlay.draw_mode = "text"
        self.overlay.draw_actions = [
            {
                "type": "text",
                "color": QColor("#33CC33"),
                "text": "Hello",
                "pos": QPoint(80, 40),
                "font_size": 18,
            }
        ]

        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(84, 46),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(104, 60),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release_event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(104, 60),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.overlay.mousePressEvent(press_event)
        self.assertTrue(self.overlay.is_moving_action)
        self.assertFalse(self.overlay.text_input.isVisible())

        self.overlay.mouseMoveEvent(move_event)
        self.overlay.mouseReleaseEvent(release_event)

        self.assertEqual(self.overlay.draw_actions[0]["pos"], QPoint(100, 54))

    def test_text_tool_double_click_reopens_existing_text_for_editing(self):
        self.overlay.selection_rect = QRect(0, 0, 300, 200)
        self.overlay.draw_mode = "text"
        self.overlay.draw_actions = [
            {
                "type": "text",
                "color": QColor("#33CC33"),
                "text": "Hello",
                "pos": QPoint(80, 40),
                "font_size": 18,
            }
        ]

        double_click_event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(84, 46),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.overlay.mouseDoubleClickEvent(double_click_event)

        self.assertFalse(self.overlay.text_input.isHidden())
        self.assertEqual(self.overlay.text_input.text(), "Hello")
        self.assertEqual(self.overlay.editing_text_index, 0)
        self.assertEqual(len(self.overlay.draw_actions), 0)

    def test_undo_and_redo_restore_moved_annotation_position(self):
        original_line = {
            "type": "line",
            "color": QColor("#3399FF"),
            "points": [QPoint(10, 10), QPoint(30, 20)],
            "thickness": 3,
        }
        self.overlay.draw_actions = [self.overlay._clone_action(original_line)]

        self.overlay._record_undo_state()
        ScreenshotOverlay._translate_action(self.overlay.draw_actions[0], QPoint(12, 6))

        self.overlay.undo_action()
        self.assertEqual(
            self.overlay.draw_actions[0]["points"], original_line["points"]
        )

        self.overlay.redo_action()
        self.assertEqual(
            self.overlay.draw_actions[0]["points"], [QPoint(22, 16), QPoint(42, 26)]
        )

    def test_finalize_capture_manual_save_skips_auto_save(self):
        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor("#FFFFFF"))

        def _config_value(key, default=None):
            return {
                "screenshot_auto_copy": False,
                "screenshot_auto_pin": False,
                "screenshot_auto_save": True,
            }.get(key, default)

        with patch.object(
            self.overlay, "get_selected_pixmap", return_value=pixmap
        ), patch.object(
            self.overlay, "_save_pixmap_to_path", return_value="C:/tmp/shot.png"
        ) as save_mock, patch.object(
            self.overlay, "_auto_save_pixmap"
        ) as auto_save_mock, patch.object(
            self.overlay, "close_overlay"
        ) as close_mock, patch(
            "src.ui.screenshot_overlay.config_manager.get_value",
            side_effect=_config_value,
        ):
            self.overlay.finalize_capture(manual_save_path="C:/tmp/shot.png")

        save_mock.assert_called_once_with(
            pixmap, "C:/tmp/shot.png", source="manual"
        )
        auto_save_mock.assert_not_called()
        close_mock.assert_called_once()

    def test_selected_pixmap_uses_native_pixels_for_high_dpi_capture(self):
        screen_pixmap = QPixmap(200, 160)
        screen_pixmap.setDevicePixelRatio(2.0)
        screen_pixmap.fill(QColor("#112233"))

        self.overlay.screen_pixmap = screen_pixmap
        self.overlay.screen_image = screen_pixmap.toImage()
        self.overlay.screen_virtual_rect = QRect(0, 0, 100, 80)
        self.overlay.screen_capture_sources = [
            {
                "geometry": QRect(0, 0, 100, 80),
                "pixmap": screen_pixmap,
                "scale": 2.0,
            }
        ]
        self.overlay.screen_scale = 2.0
        self.overlay.selection_rect = QRect(10, 12, 30, 20)

        selected = self.overlay.get_selected_pixmap()

        self.assertIsNotNone(selected)
        self.assertEqual(selected.width(), 60)
        self.assertEqual(selected.height(), 40)
        self.assertEqual(selected.devicePixelRatio(), 2.0)
        self.assertEqual(selected.deviceIndependentSize().width(), 30)
        self.assertEqual(selected.deviceIndependentSize().height(), 20)


if __name__ == "__main__":
    unittest.main()
