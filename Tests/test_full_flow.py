import pytest
import threading
import time
from client.theme_manager import ThemeManager
from client.window_manager import WindowManager
from client.app_controller import AppController
# If your relay server is class-based, import it; otherwise, use subprocess
# from relay_server.server import RelayServer
import subprocess
import sys

@pytest.fixture(scope="module")
def relay_server():
    # If you have a class-based server, use that. Otherwise, use subprocess.
    proc = subprocess.Popen([sys.executable, '-m', 'relay_server.server'])
    time.sleep(1)  # Wait for server to start
    yield proc
    proc.terminate()
    proc.wait()

@pytest.fixture
def controller_ali(qtbot, relay_server):
    theme_manager = ThemeManager()
    window_manager = WindowManager(theme_manager)
    ctrl = AppController(window_manager)
    qtbot.addWidget(ctrl.wm.login_window)
    return ctrl

@pytest.fixture
def controller_mia(qtbot, relay_server):
    theme_manager = ThemeManager()
    window_manager = WindowManager(theme_manager)
    ctrl = AppController(window_manager)
    qtbot.addWidget(ctrl.wm.login_window)
    return ctrl

def test_end_to_end_flow(qtbot, controller_ali, controller_mia):
    # 1. ali login
    wm_a = controller_ali.wm
    wm_a.login_requested.emit("127.0.0.1:9009", "ali", "123", True)
    qtbot.waitUntil(lambda: hasattr(wm_a, "controller_window") and wm_a.controller_window.isVisible(), timeout=3000)

    # 2. mia login
    wm_b = controller_mia.wm
    wm_b.login_requested.emit("127.0.0.1:9009", "mia", "12", False)
    qtbot.waitUntil(lambda: hasattr(wm_b, "controller_window") and wm_b.controller_window.isVisible(), timeout=3000)

    # 3. ali share, mia view
    win_a = wm_a.controller_window
    win_b = wm_b.controller_window
    win_a.share_button.click()
    win_b.peer_input.setText("ali")  # یا UID عددی مثل "101"
    win_b.view_button.click()
    qtbot.wait(1000)
    assert hasattr(win_b, 'screen_lbl') and win_b.screen_lbl.pixmap() is not None

    # 4. mia → ali chat
    win_b.chat_input.setText("سلام ali")
    win_b.chat_send_button.click()
    qtbot.wait(300)
    assert "سلام ali" in win_a.chat_disp.toPlainText()

    # 5. ali → mia chat
    win_a.chat_input.setText("سلام mia")
    win_a.chat_send_button.click()
    qtbot.wait(300)
    assert "سلام mia" in win_b.chat_disp.toPlainText()

    # 6. ali logout
    win_a.logout_btn.click()
    qtbot.wait(300)
    assert wm_a.login_window.isVisible()
    assert "ali has logged out" in win_b.chat_disp.toPlainText()

    # 7. server crash
    relay_server.terminate()
    qtbot.wait(500)
    assert "-- Server disconnected --" in win_b.chat_disp.toPlainText()
    assert wm_b.login_window.isVisible() 