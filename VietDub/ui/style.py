"""Giao diện tối, gọn, chữ rõ."""

ACCENT = "#7C5CFF"
QSS = f"""
* {{ font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 10pt; color: #E6E8EF; }}
QMainWindow, QDialog, QWidget#root {{ background: #0E1118; }}
QFrame#card {{ background: #151925; border: 1px solid #262C3D; border-radius: 14px; }}
QLabel#cardTitle {{ font-size: 11.5pt; font-weight: 700; color: #FFFFFF; }}
QLabel#title {{ font-size: 17pt; font-weight: 800; color: #FFFFFF; }}
QLabel#muted {{ color: #8C93A8; }}
QLabel#badge {{ background: #12302A; color: #9BF0D6; border: 1px solid #1E7A63; border-radius: 10px; padding: 3px 10px; }}
QLabel#badgeOnline {{ background: #2A2160; color: #D7CCFF; border: 1px solid {ACCENT}; border-radius: 10px; padding: 3px 10px; }}
QFrame#drop {{ border: 2px dashed #3A4160; border-radius: 14px; background: #121623; }}
QFrame#drop[hover="true"] {{ border-color: {ACCENT}; background: #1A1830; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: #0F121A; border: 1px solid #2A3043; border-radius: 8px; padding: 6px 8px; selection-background-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: #151925; border: 1px solid #2A3043; selection-background-color: #3A2F7A; }}
QPushButton {{ background: #1F2433; border: 1px solid #2F3650; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ background: #283048; }}
QPushButton:disabled {{ color: #5A6075; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; font-weight: 700; }}
QPushButton#primary:hover {{ background: #8E73FF; }}
QPushButton#big {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 #14C2A8); border: none;
    color: white; font-weight: 800; font-size: 12.5pt; padding: 12px 22px; border-radius: 12px; }}
QPushButton#big:disabled {{ background: #2A2F40; color: #6C7489; }}
QPushButton#danger {{ background: #3A1F29; border: 1px solid #5A2A3A; color: #FF9AAE; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3A4058; background: #0F121A; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QTableWidget {{ background: #0F121A; border: 1px solid #2A3043; border-radius: 10px; gridline-color: #222839; }}
QHeaderView::section {{ background: #171B28; color: #AEB4C8; border: none; padding: 6px; font-weight: 600; }}
QTableWidget::item:selected {{ background: #3A2F7A; }}
QProgressBar {{ background: #0F121A; border: 1px solid #2A3043; border-radius: 8px; text-align: center; height: 18px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 #14C2A8); border-radius: 7px; }}
QPlainTextEdit#log {{ font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 9pt; color: #AEB4C8; }}
QLabel#chip {{ background: #181C28; border: 1px solid #2A3043; border-radius: 9px; padding: 6px 10px; color: #8C93A8; }}
QLabel#chip[state="start"] {{ background: #2A2160; border-color: {ACCENT}; color: #FFFFFF; font-weight: 700; }}
QLabel#chip[state="done"] {{ background: #12302A; border-color: #1E7A63; color: #9BF0D6; }}
QLabel#chip[state="skip"] {{ color: #5A6075; }}
QLabel#chip[state="fail"] {{ background: #3A1F29; border-color: #A0405A; color: #FF9AAE; }}
QPushButton#update {{ background: #12302A; border: 1px solid #1E7A63; color: #9BF0D6; font-weight: 700; }}
QPushButton#preset {{ background: #1A1F30; border: 1px solid #343B57; border-radius: 9px; padding: 6px 10px; }}
QPushButton#preset:hover {{ border-color: {ACCENT}; }}
QLabel#status {{ background: #121623; border: 1px solid #262C3D; border-radius: 10px; padding: 4px 10px; color: #AEB4C8; }}
QFrame#player {{ background: #000000; border: 1px solid #262C3D; border-radius: 10px; }}
QLabel#thumb {{ background: #000000; border: 1px solid #262C3D; border-radius: 10px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2F3650; border-radius: 5px; min-height: 30px; }}
"""
