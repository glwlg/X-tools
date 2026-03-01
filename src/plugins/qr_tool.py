import qrcode
from PIL import ImageQt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from src.core.plugin_base import PluginBase
from src.ui.pinned_image_window import PinnedImageWindow
from src.core.logger import get_logger


logger = get_logger(__name__)


class QRCodePlugin(PluginBase):
    def __init__(self):
        self.pinned_windows = []

    def get_name(self):
        return "二维码生成"

    def get_description(self):
        return "生成二维码并在屏幕上贴图展示"

    def get_keywords(self):
        return ["qr", "qrcode"]

    def get_command_schema(self):
        return {
            "usage": "qr <text>",
            "examples": ["qr https://x-tools.app", "qrcode hello"],
            "params": [
                {
                    "name": "text",
                    "label": "二维码内容",
                    "placeholder": "输入文本或链接",
                    "required": True,
                }
            ],
        }

    def execute(self, query):
        query = query.strip()
        if not query:
            return [{"name": "输入内容以生成二维码", "path": "", "type": "info"}]

        return [
            {
                "name": f"生成二维码: {query}",
                "path": query,
                "type": "qr_generate",
            }
        ]

    def handle_action(self, query):
        if not query:
            return

        try:
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(query)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Convert PIL image to QPixmap
            qim = ImageQt.ImageQt(img.convert("RGBA"))
            pixmap = QPixmap.fromImage(qim)

            # Show as pinned window
            pin_win = PinnedImageWindow(pixmap)

            # Center on screen
            screen = QApplication.primaryScreen()
            if screen:
                screen_geom = screen.geometry()
                x = (screen_geom.width() - pixmap.width()) // 2
                y = (screen_geom.height() - pixmap.height()) // 2
                pin_win.move(x, y)

            pin_win.show()
            self.pinned_windows.append(pin_win)

        except Exception as e:
            logger.exception("QR Generation Error: %s", e)

    def on_enter(self):
        pass

    def on_exit(self):
        pass
