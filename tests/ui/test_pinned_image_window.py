import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from src.ui.pinned_image_window import ImageLabel, PinnedImageWindow


_APP = QApplication.instance() or QApplication([])


class TestImageLabelSelectionBehavior(unittest.TestCase):
    def test_mouse_release_does_not_auto_copy_selection(self):
        label = ImageLabel()
        label.is_selecting = True
        label.has_selection = True

        event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(8.0, 8.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        with patch.object(label, "copy_selection") as copy_mock:
            label.mouseReleaseEvent(event)

        copy_mock.assert_not_called()

    def test_selection_starts_only_after_drag(self):
        label = ImageLabel()
        label.ocr_lines = [{"text": "hello", "rect": (0, 0, 100, 20)}]

        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10.0, 10.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        label.mousePressEvent(press_event)
        self.assertFalse(label.has_selection)

        move_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(30.0, 10.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        label.mouseMoveEvent(move_event)
        self.assertTrue(label.has_selection)

    def test_get_selected_text_keeps_left_to_right_order_in_same_row(self):
        label = ImageLabel()
        label.ocr_lines = [
            {"text": "SDK loaded", "rect": (80, 8, 120, 20)},
            {"text": "Everything", "rect": (0, 10, 75, 20)},
        ]
        label.selection_start = QPoint(0, 18)
        label.selection_end = QPoint(210, 18)
        label.has_selection = True

        selected = label.get_selected_text()

        self.assertEqual(selected, "Everything SDK loaded")

    def test_get_selected_text_ignores_prev_box_overlap_char(self):
        label = ImageLabel()
        label.ocr_lines = [
            {"text": "everything:", "rect": (0, 10, 100, 20)},
            {"text": "Everything SDK loaded", "rect": (95, 10, 210, 20)},
        ]
        label.selection_start = QPoint(95, 20)
        label.selection_end = QPoint(300, 20)
        label.has_selection = True

        selected = label.get_selected_text()

        self.assertEqual(selected, "Everything SDK loaded")

    def test_get_selected_text_preserves_leading_char_when_start_near_left_edge(self):
        label = ImageLabel()
        label.ocr_lines = [{"text": "Click", "rect": (100, 10, 30, 20)}]
        label.selection_start = QPoint(106, 20)
        label.selection_end = QPoint(130, 20)
        label.has_selection = True

        selected = label.get_selected_text()

        self.assertEqual(selected, "Click")

    def test_join_row_fragments_adds_space_for_small_gap(self):
        fragments = [
            {"text": "Click", "x0": 0, "x1": 40, "char_w": 8.0},
            {"text": "https://qf", "x0": 42, "x1": 114, "char_w": 8.0},
        ]

        out = ImageLabel._join_row_fragments(fragments)

        self.assertEqual(out, "Click https://qf")


class TestPinnedImageWindowOCRBehavior(unittest.TestCase):
    def test_on_ocr_finished_does_not_show_success_toast(self):
        pixmap = QPixmap(20, 20)
        window = PinnedImageWindow(pixmap)

        results = [
            (
                [[0, 0], [10, 0], [10, 10], [0, 10]],
                "hello",
            )
        ]

        with patch.object(window, "show_toast") as toast_mock:
            window.on_ocr_finished(results)

        self.assertEqual(len(window.image_label.ocr_lines), 1)
        self.assertEqual(window.image_label.ocr_lines[0]["text"], "hello")
        toast_mock.assert_not_called()
        window.close()

    def test_copy_selected_ocr_text_copies_to_clipboard(self):
        pixmap = QPixmap(20, 20)
        window = PinnedImageWindow(pixmap)
        window.image_label.ocr_lines = [{"text": "hello", "rect": (0, 0, 100, 20)}]
        window.image_label.selection_start = QPoint(0, 10)
        window.image_label.selection_end = QPoint(99, 10)
        window.image_label.has_selection = True

        with patch.object(window, "show_toast") as toast_mock:
            window.copy_selected_ocr_text()

        clipboard = QApplication.clipboard()
        self.assertIsNotNone(clipboard)
        self.assertEqual("" if clipboard is None else clipboard.text(), "hello")
        toast_mock.assert_called_once_with("选中文本已复制")
        window.close()

    def test_show_toast_ignores_deleted_previous_label_reference(self):
        class _DeadLabel:
            def hide(self):
                raise RuntimeError(
                    "wrapped C/C++ object of type QLabel has been deleted"
                )

            def deleteLater(self):
                raise RuntimeError(
                    "wrapped C/C++ object of type QLabel has been deleted"
                )

            def __bool__(self):
                return True

        pixmap = QPixmap(20, 20)
        window = PinnedImageWindow(pixmap)
        setattr(window, "toast_label", _DeadLabel())

        try:
            window.show_toast("ok", duration=10)
        except RuntimeError as exc:
            self.fail(f"show_toast raised unexpectedly: {exc}")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
