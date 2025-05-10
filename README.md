# SCU Remote Desktop

SCU Remote Desktop is a cross-platform desktop-sharing and remote-control application, inspired by tools like AnyDesk. It enables users to share their screen, control remote machines, and communicate via chat, all facilitated by a central relay server. While designed to be cross-platform, some features like high-fidelity screen capture and remote input control currently have better support or specific implementations on Windows.

---

## 🌟 Overview

This project aims to provide a feature-rich remote desktop experience. Users can register and log in, then act as either a "Controller" (to view and control another machine) or a "Target" (to share their screen and be controlled). Communication, including chat messages, screen data, and input events, is routed through a Python-based relay server. The application features a SQLite database for user and session management, and a PyQt5-based graphical user interface with support for theme switching.

---

## ✅ Features

*   **User Authentication:** Secure Login/Register system with SQLite backend (UID generation, password hashing).
*   **Role-Based Access:** Dynamic switching between Controller and Target roles.
*   **Real-time Chat:** One-to-one chat with a styled UI, including message bubbles and timestamps.
*   **Theme Customization:** Switch between dark (default) and light themes with saved preferences.
*   **Relay Server:** Centralized server for brokering connections and relaying data between clients.
*   **Session Management:** Tracking of active sessions between controllers and targets.
*   **Logging:** Comprehensive logging for both client and server actions, stored in the database.
*   **Admin Panel:** Interface for managing users and viewing system logs.
*   **Screen Sharing (Target → Controller):** Real-time transmission of the target's screen. (Primary implementation currently relies on Windows-specific APIs for optimal capture; other OSes might use more generic, potentially slower, methods if available via Pillow).
*   **Remote Input Control (Controller → Target):** (Relies on `pynput`, which has varying levels of support and potential setup requirements across different OSes and desktop environments).
    *   Mouse movement, clicks, and scrolling.
    *   Keyboard input.
*   **Permission System:** Controllers request permissions (view, mouse, keyboard) which targets can grant or deny.
*   **Screenshot Functionality:** Capture screenshots of the remote (controller) or local (target) screen. (Local screen capture on Target currently uses Windows-specific APIs for best results).

---

## 🛠️ Technology Stack

*   **Programming Language:** Python 3.10+
*   **GUI Framework:** PyQt5
*   **Networking:** Python `socket` and `socketserver` modules for TCP/IP communication.
*   **Database:** SQLite for storing user credentials, session information, and logs.
*   **Image Processing:** Pillow (PIL) for screen capture (including `ImageGrab` on Windows) and image manipulation.
*   **Input Control:** `pynput` for simulating mouse and keyboard events on the target machine (cross-platform, but with OS-specific considerations for full functionality, especially for listening to events).
*   **Styling:** Qt StyleSheets (QSS) for UI theming.

---

## 🗂 Folder Structure

```
navid-remote-desktop/
├── main.py                     # Entry point for the client application
├── remote_desktop_final/       # (Legacy or alternative root, structure seems to be here)
│   ├── main.py                 # Actual client entry point used in run commands
│   ├── relay.db                # SQLite database file
│   ├── client/                 # Client-side application logic and UI
│   │   ├── __init__.py
│   │   ├── app_controller.py   # Core client logic, state management
│   │   ├── window_manager.py   # Manages UI window transitions
│   │   ├── theme_manager.py    # Handles application themes
│   │   ├── controller_client.py# Network logic for controller role
│   │   ├── target_client.py    # Network logic for target role
│   │   ├── ui_login.py         # Login window UI
│   │   ├── ui_register.py      # Registration window UI
│   │   ├── ui_controller.py    # Main controller/target window UI
│   │   ├── ui_admin.py         # Admin panel UI
│   │   └── widgets/
│   │       └── chat_widget.py  # Reusable chat UI component
│   ├── relay_server/           # Server-side application logic
│   │   ├── __init__.py
│   │   ├── server.py           # Main relay server implementation
│   │   ├── database.py         # SQLite database interaction layer
│   │   ├── logger.py           # Custom logger for server events
│   │   └── config.py           # (Potentially for server configuration)
│   ├── shared/                 # Shared utilities and protocol definition
│   │   ├── __init__.py
│   │   ├── constants.py        # Shared constant values (e.g., theme paths)
│   │   ├── protocol.py         # Defines packet types and network helpers
│   │   └── utils.py            # (Potentially for shared utility functions)
│   ├── assets/                 # Static assets like icons and stylesheets
│   │   ├── icons/              # Application icons
│   │   └── styles/             # QSS theme files (default.qss, light_styles.qss)
│   ├── requirements.txt        # Python package dependencies
│   └── Tests/                  # Unit and integration tests
│       ├── __init__.py
│       ├── conftest.py
│       └── test_*.py           # Individual test files
├── credentials.json            # Stores 'remember me' credentials locally (client-side)
├── settings.json               # Stores client-side settings like preferred theme
├── pyproject.toml              # Project metadata and dependencies for build systems
├── pytest.ini                  # Pytest configuration
├── README.md                   # This file
└── .gitignore                  # Specifies intentionally untracked files
```

*(Note: The primary application code seems to reside within `remote_desktop_final/`. The top-level `main.py` might be a launcher or an older entry point.)*

---

## ⚙️ Prerequisites

*   Python 3.10 or higher.
*   `pip` (Python package installer).

#### Cross-Platform Considerations:
*   **Core Functionality:** The application is designed to be cross-platform (Windows, macOS, Linux). The relay server and basic client communication (authentication, chat) should work consistently across platforms.
*   **Windows:** Offers the most complete feature set for screen sharing and control due to mature OS APIs and the use of `pywin32` for:
    *   Optimized screen capture via `ImageGrab` (often uses GDI).
    *   Accurate system metrics (`GetSystemMetrics`).
    *   Cursor capture during screen sharing/screenshots from the Target machine.
*   **macOS:**
    *   **Screen Capture (Target Role):** Relies on Pillow's `ImageGrab.grab()`. This typically uses the built-in `screencapture` utility. Cursor capture is generally **not** included with this method. Performance may vary.
    *   **Remote Input Control (`pynput`):**
        *   **Sending Input (Controller Role):** Generally works.
        *   **Receiving Input (Target Role):** Requires explicit accessibility permissions. Users must go to `System Settings > Privacy & Security > Accessibility` and add their terminal or the bundled application to the list of allowed apps. Without this, `pynput` cannot monitor or control mouse/keyboard events.
*   **Linux:**
    *   **Screen Capture (Target Role):** Relies on Pillow's `ImageGrab.grab()`. The backend for this can vary:
        *   On X11 sessions, it often tries to use utilities like `scrot` or `gnome-screenshot`. If these are not installed, `ImageGrab.grab()` may fail or return a blank image. Users might need to install one: `sudo apt install scrot` or `sudo apt install gnome-screenshot`.
        *   On Wayland sessions, screen capture can be more restrictive. `ImageGrab.grab()` might not work, or might only capture the current application window, depending on the compositor and installed portal frontends (e.g., `xdg-desktop-portal`). Capturing the entire screen reliably on Wayland often requires more specialized tools or APIs not directly used by Pillow's default `ImageGrab`.
        *   Cursor capture is generally **not** included with `ImageGrab.grab()`.
    *   **Remote Input Control (`pynput`):**
        *   **Sending Input (Controller Role):** Generally works on X11. May have issues on Wayland depending on the compositor.
        *   **Receiving Input (Target Role):** Works best on X11. On Wayland, `pynput`'s ability to listen for global keyboard/mouse events is often restricted for security reasons. Some desktop environments might offer workarounds or require specific configurations.
*   **`pywin32` Dependency:** This package is Windows-specific and will only be installed/functional on Windows. Code sections relying on it have fallbacks for other OSes, but this means certain Windows-specific optimizations or features (like detailed screen metrics or robust cursor capture on Target) will not be available elsewhere.

---

## 🚀 Setup and Installation

1.  **Clone the repository (if you haven't already):**
    ```bash
    git clone <repository-url>
    cd navid-remote-desktop
    ```

2.  **Navigate to the project directory:**
    The main operational directory seems to be `remote_desktop_final`. Most commands should be run from there or relative to it.
    ```bash
    cd remote_desktop_final
    ```
    *(If `requirements.txt` is in the parent `navid-remote-desktop` directory, run pip install from there)*

3.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

4.  **Install dependencies:**
    Make sure your `requirements.txt` is up-to-date.
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: The `pywin32` package listed in `requirements.txt` is Windows-specific. `pip` will skip installing it on macOS and Linux. Functionality relying on it (primarily advanced screen capture features on the Target machine) will use cross-platform fallbacks on non-Windows systems, which may have different characteristics or limitations, e.g., no cursor capture.)*
    *(If `requirements.txt` is in the root `navid-remote-desktop` directory, use `pip install -r ../requirements.txt` if you are in `remote_desktop_final`)*

---

## 🏁 How to Run

### 1️⃣ Start the Relay Server

Open a terminal:
```bash
cd remote_desktop_final/relay_server
python server.py
```
The server will start listening on `0.0.0.0:9009` by default.

### 2️⃣ Start Client #1 (e.g., as Controller)

In another terminal:
```bash
cd remote_desktop_final
python main.py
```
Login with a registered user (e.g., `ali`) and select the "Controller" role.

### 3️⃣ Start Client #2 (e.g., as Target)

In a third terminal (or on another machine on the same network):
```bash
cd remote_desktop_final
python main.py
```
Login with a different registered user (e.g., `mia`) and select the "Target" role.

---

## 🕹️ Usage

1.  **Login/Register:**
    *   Use the login screen to enter your credentials. The default server address is `127.0.0.1:9009`.
    *   If you don't have an account, click "Create Account" to register.
    *   You can choose to log in as a "Controller" or "Target".
    *   Admin login: `admin`/`admin` to access the Admin Panel.

2.  **Connecting (Controller Role):**
    *   Once logged in as a Controller, enter the **Username** or **User ID (UID)** of the Target client in the toolbar.
    *   Click the "Connect" button.

3.  **Session:**
    *   If the Target is available and accepts, a session will be established.
    *   The UI will indicate the connection status and peer username.

4.  **Chat:**
    *   Once connected, use the chat panel on the right to send and receive messages with the peer.

5.  **Requesting Permissions (Controller Role):**
    *   In the "Permissions" group box, check the desired permissions (View Screen, Control Mouse, Control Keyboard).
    *   Click "Request/Update Permissions". The Target client will receive a dialog to approve or deny these.

6.  **Screen Viewing (Controller Role):**
    *   If "View Screen" permission is granted by the Target, their screen will appear in the main display area.

7.  **Remote Control (Controller Role):**
    *   If "Control Mouse" and/or "Control Keyboard" permissions are granted, you can control the Target's machine by interacting with the displayed remote screen.

8.  **Theme Switching:**
    *   Click the 🌙/☀️ icon in the toolbar (or login/register screen) to toggle between dark and light themes. Your preference is saved.

9.  **Switching Roles:**
    *   Click the "Switch Role" button in the main window toolbar. This will log you out and allow you to log back in with a different role using the same or different credentials.

10. **Admin Panel:**
    *   Log in with `admin`/`admin`.
    *   **User Management Tab:** View, add, edit, and delete users.
    *   **Advanced Logs Tab:** View detailed system logs with filtering options.

11. **Taking Screenshots:**
    *   Click the camera icon in the toolbar.
    *   A file dialog will appear to save the screenshot.
    *   **Controller:** Captures the current view of the remote screen.
    *   **Target:** Captures its own local screen.

13. **Screen Recording:**
    *   Click the recorder icon in the toolbar to start/stop recording.
    *   Recorded frames are saved as a sequence of JPEG images in a timestamped folder (usually under `~/Pictures/SCURemoteRecordings/` or a local `recordings/` folder if the Pictures directory is not accessible).
    *   When recording stops, the application will display a message indicating the path to the saved frames and provide an example FFmpeg command to compile these images into a video.
    *   **Example FFmpeg command (requires FFmpeg to be installed separately):**
        ```bash
        ffmpeg -framerate 10 -i "path/to/your/recording_folder/frame_%05d.jpg" -c:v libx264 -pix_fmt yuv420p output.mp4
        ```
    *   Replace `"path/to/your/recording_folder/"` with the actual path to the directory containing the `frame_XXXXX.jpg` files. The `-framerate 10` assumes the frames were captured at approximately 10 FPS; adjust if needed. `output.mp4` is the desired name for the compiled video file.

---

## 🧩 Project Components

### Client (`remote_desktop_final/client/`)

*   **`main.py`**: The main entry point for launching the client application. Initializes logging, the Qt application, `ThemeManager`, `WindowManager`, and `AppController`. (Note: there's also a `main.py` inside `remote_desktop_final/` which seems to be the one executed by the run commands).
*   **`app_controller.py` (`AppController`)**: The brain of the client application.
    *   Handles user login, registration, and logout logic.
    *   Manages the client's current state (username, role, session, peer).
    *   Interfaces with `ControllerClient` or `TargetClient` for network communication.
    *   Processes incoming data from the server (chat messages, permissions, frames, input commands).
    *   Sends user actions (chat, connection requests, permission requests, input events, frames) to the server.
    *   Communicates with `WindowManager` via Qt signals to update the UI.
    *   Handles admin panel operations.
*   **`window_manager.py` (`WindowManager`)**:
    *   Manages the lifecycle and transitions between different UI windows (`LoginWindow`, `RegistrationWindow`, `ControllerWindow`, `AdminWindow`).
    *   Connects UI signals from windows to `AppController` slots and vice-versa.
    *   Handles theme switching requests and applies themes to the application.
    *   Shows system messages, errors, and dialogs (like permission requests).
*   **`theme_manager.py` (`ThemeManager`)**:
    *   Loads QSS stylesheets from `assets/styles/`.
    *   Applies the selected theme (dark/light) to the application.
    *   Saves and loads the user's theme preference from `settings.json`.
*   **UI Files:**
    *   **`ui_login.py` (`LoginWindow`)**: Defines the login form UI, emits signals for login attempts and registration requests.
    *   **`ui_register.py` (`RegistrationWindow`)**: Defines the user registration form UI, emits signals for registration attempts.
    *   **`ui_controller.py` (`ControllerWindow`, `InputForwardingLabel`)**: The main application window used by both Controller and Target roles.
        *   Displays toolbars for connection, actions (screenshot, recording - recording saves image sequences), theme, logout.
        *   Contains the screen display area (`InputForwardingLabel` for controllers to capture input).
        *   Includes the sidebar for permissions (controller) and the chat area.
        *   Emits signals for user actions like connect, send chat, request permissions, send input, send frames.
    *   **`ui_admin.py` (`AdminWindow`, `UserEditDialog`)**: Defines the UI for the admin panel, including user management and log viewing tables and dialogs.
*   **Client Types:**
    *   **`controller_client.py` (`ControllerClient`)**: Handles network communication for a client in the "Controller" role. Establishes connection, sends/receives control packets (connect, permissions, input, chat), and receives screen frames.
    *   **`target_client.py` (`TargetClient`)**: Handles network communication for a client in the "Target" role. Responds to connection/permission requests, sends screen frames, receives input commands, and handles chat.
*   **Widgets:**
    *   **`widgets/chat_widget.py` (`ChatAreaWidget`, `ChatBubble`)**: A custom widget that displays chat messages in styled bubbles, similar to modern messaging apps. Supports RTL/LTR text and theme changes.

### Relay Server (`remote_desktop_final/relay_server/`)

*   **`server.py` (`RelayHandler`, `CustomThreadingTCPServer`)**: The core of the relay server.
    *   Uses `ThreadingTCPServer` to handle multiple client connections concurrently.
    *   `RelayHandler` instances manage individual client connections.
    *   Handles client authentication against the database.
    *   Manages active client connections and their session states (paired controller/target).
    *   Relays packets (CONNECT, PERM, CHAT, FRAME, INPUT) between appropriate peers.
    *   Logs server events and client interactions to the console and database.
*   **`database.py` (`Database`)**:
    *   Provides an interface to the SQLite database (`relay.db`).
    *   Manages tables for `users`, `sessions`, `chat_msgs`, and `logs`.
    *   Handles user registration, authentication, status updates, and admin operations (list, edit, delete users).
    *   Manages session creation and closure.
    *   Stores chat messages and system logs.
*   **`logger.py` (`DBHandler`, `get_logger`)**:
    *   Custom logging handler (`DBHandler`) that writes log records to the SQLite `logs` table.
    *   `get_logger` function to obtain a logger instance configured with both console and database handlers.

### Shared (`remote_desktop_final/shared/`)

*   **`protocol.py` (`PacketType`, send/recv functions, image encoding/decoding)**:
    *   `PacketType` (Enum): Defines all types of messages exchanged between clients and the server (e.g., `AUTH_REQ`, `FRAME`, `CHAT`).
    *   `send_json()`, `send_bytes()`: Functions to serialize and send data over sockets with a length prefix.
    *   `recv()`: Function to receive and deserialize data from sockets.
    *   `encode_image()`, `decode_image()`: Utilities to compress (PNG/JPEG with zlib) and decompress PIL Images for efficient network transfer.
*   **`constants.py`**: Defines shared constants, such as `DEFAULT_THEME` and `STYLES_DIR`.

### Assets (`remote_desktop_final/assets/`)

*   **`icons/`**: Contains various `.png` and `.svg` icons used throughout the UI.
*   **`styles/`**: Contains QSS (Qt Style Sheets) files for theming:
    *   `default.qss`: Dark theme stylesheet.
    *   `light_styles.qss`: Light theme stylesheet.
    *   `chat_styles.qss`: Specific styles for the chat widget, potentially merged or referenced by main theme files.

### Tests (`remote_desktop_final/Tests/`)

*   Contains PyTest unit and integration tests for various components like the database, protocol, and server logic.
*   `conftest.py` likely sets up the Python path for tests.

---

## 🧪 Tests

To run the unit tests:

1.  Navigate to the project's root directory (where `pytest.ini` is located, likely `navid-remote-desktop/` or `remote_desktop_final/` if tests are configured to run from there).
2.  Ensure your virtual environment is activated.
3.  Run PyTest:
    ```bash
    pytest
    ```
    Or for a quieter output:
    ```bash
    pytest -q
    ```

---

## 🛣️ Roadmap & Future Enhancements

*   **Improved Performance for Screen Streaming:** Optimize image encoding, compression, and rendering for smoother, higher FPS screen sharing.
*   **Refined Login/Logout Flow:** Enhance user feedback and streamline transitions.
*   **Session Recording:** Convert image sequence recordings into video files (e.g., using FFmpeg externally or integrating a library).
*   **File Transfer:** Add drag & drop file transfer capabilities.
*   **Multi-Monitor Support:** Allow selection and switching between target's displays.
*   **Auto-Reconnect:** Implement logic for automatic reconnection if the connection drops.
*   **Metrics Dashboard:** Display real-time FPS, bandwidth, and latency.
*   **Clipboard Sharing:** Synchronize clipboard content between peers.
*   **Security Enhancements:**
    *   Implement TLS/SSL for encrypted communication.
    *   Token-based backend API integration (as mentioned in old README).
*   **Cross-Platform Enhancements:**
    *   Implement robust, performant screen capture for macOS and Linux, including cursor capture if possible (e.g., using `mss` or platform-specific libraries).
    *   Investigate and improve `pynput` functionality and setup guidance across all platforms, especially for Wayland on Linux and accessibility on macOS.
    *   Further abstract or provide alternatives for any remaining Windows-specific API calls to ensure feature parity where feasible.
*   **Full Session Log Viewer & Admin Dashboard Enhancements:** Expand admin capabilities.
*   **CLI Client:** Develop a command-line interface for headless operation or scripting.

---

## 🤝 Contributing

Contributions are welcome! Please follow the standard GitHub flow:
1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/YourFeature`).
3.  Commit your changes (`git commit -m 'Add some feature'`).
4.  Push to the branch (`git push origin feature/YourFeature`).
5.  Open a Pull Request.

Please ensure your code adheres to existing style and that tests pass.

---

## 📜 License

(To be determined - e.g., MIT License, Apache 2.0. Consider adding a `LICENSE` file.)

---

## 💬 Contact

For help or suggestions, contact the SCU Remote Team. (Or add specific contact details/repository issue tracker).
