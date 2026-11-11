"""Giao diện tối hiện đại."""

ACCENT = "#7C5CFF"
ACCENT2 = "#00C2A8"

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; font-size: 10pt; color: #E6E8EF; }}
QMainWindow, QWidget#root {{ background: #12141C; }}
QWidget {{ background: transparent; }}
QDialog {{ background: #171A24; }}
QFrame#sidebar {{ background: #0D0F15; border-right: 1px solid #232838; }}
QListWidget#nav {{ background: transparent; border: none; outline: none; padding: 6px; }}
QListWidget#nav::item {{ padding: 12px 14px; margin: 3px 4px; border-radius: 10px; color: #AEB4C8; }}
QListWidget#nav::item:hover {{ background: #1B1F2C; color: #FFFFFF; }}
QListWidget#nav::item:selected {{ background: {ACCENT}; color: white; font-weight: 600; }}
QListWidget#subnav {{ background: #141824; border: 1px solid #2A3043; border-radius: 12px; padding: 6px; outline: none; }}
QListWidget#subnav::item {{ padding: 9px 10px; margin: 2px 2px; border-radius: 8px; color: #C3C8D8; }}
QListWidget#subnav::item:hover {{ background: #1F2433; color: #FFFFFF; }}
QListWidget#subnav::item:selected {{ background: #3A2F7A; color: white; font-weight: 600; }}
QLabel#appTitle {{ font-size: 15pt; font-weight: 700; color: white; padding: 16px 14px 2px 14px; }}
QLabel#appSub {{ color: #7D849B; padding: 0 14px 12px 14px; font-size: 9pt; }}
QLabel#pageTitle {{ font-size: 17pt; font-weight: 700; color: white; }}
QLabel#pageHint {{ color: #8C93A8; }}
QLabel#muted {{ color: #8C93A8; }}
QLabel#ok {{ color: #3DDC97; }}
QLabel#err {{ color: #FF6B81; }}
QLabel#badge {{ background: #232838; border-radius: 8px; padding: 4px 10px; color: #C9CEDD; }}
QGroupBox {{ background: #181B26; border: 1px solid #262B3B; border-radius: 12px; margin-top: 16px;
             padding: 14px 12px 12px 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #B9A8FF; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextBrowser {{
    background: #0F121A; border: 1px solid #2A3043; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #171A24; border: 1px solid #2A3043; selection-background-color: {ACCENT}; }}
QPushButton {{ background: #262B3B; border: 1px solid #323850; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ background: #30364A; }}
QPushButton:pressed {{ background: #1E2230; }}
QPushButton:disabled {{ color: #5C6275; background: #1A1D27; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: #8E73FF; }}
QPushButton#big {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2});
    border: none; color: white; font-size: 12pt; font-weight: 700; padding: 12px 22px; border-radius: 12px; }}
QPushButton#big:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8E73FF, stop:1 #19D6BD); }}
QPushButton#danger {{ background: #3A1F29; border: 1px solid #5A2A3A; color: #FF9AAE; }}
QPushButton#link {{ background: transparent; border: none; color: #8FB4FF; padding: 2px 4px; text-decoration: underline; }}
QTableWidget, QListWidget {{ background: #0F121A; border: 1px solid #2A3043; border-radius: 10px;
    gridline-color: #232838; alternate-background-color: #141823; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: #3A2F7A; color: white; }}
QListWidget::item {{ padding: 5px 6px; }}
QHeaderView::section {{ background: #1B1F2C; color: #AEB4C8; border: none; border-right: 1px solid #232838;
    padding: 6px; font-weight: 600; }}
QProgressBar {{ background: #0F121A; border: 1px solid #2A3043; border-radius: 8px; text-align: center; height: 18px; }}
QProgressBar::chunk {{ border-radius: 7px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2}); }}
QSlider::groove:horizontal {{ height: 6px; background: #2A3043; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; margin: -6px 0; border-radius: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3A4058; background: #0F121A; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QRadioButton {{ spacing: 8px; padding: 3px 0; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 2px solid #4A5170; background: #0F121A; }}
QRadioButton::indicator:checked {{ background: {ACCENT}; border: 2px solid #C9BEFF; }}
QRadioButton:checked {{ color: #FFFFFF; font-weight: 600; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2E3448; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QTabWidget::pane {{ border: 1px solid #262B3B; border-radius: 10px; }}
QTabBar::tab {{ background: #181B26; padding: 8px 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {ACCENT}; color: white; }}
QFrame#drop {{ border: 2px dashed #3A4058; border-radius: 16px; background: #151823; }}
QFrame#drop[hover="true"] {{ border-color: {ACCENT}; background: #1B1830; }}
QFrame#card {{ background: #181B26; border: 1px solid #262B3B; border-radius: 12px; }}
QFrame#bottombar {{ background: #0D0F15; border-top: 1px solid #232838; }}
QPlainTextEdit#log {{ font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace; font-size: 9pt; }}
QToolTip {{ background: #232838; color: white; border: 1px solid #3A4058; padding: 6px; }}
"""
