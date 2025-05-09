# SCU Remote Desktop

SCU Remote Desktop is a Windows-only desktop-sharing and remote-control application, inspired by tools like AnyDesk.
It supports real-time screen sharing, chat, mouse/keyboard control, dynamic user roles (Controller/Target), and a centralized relay server for secure communication.

---

## ✅ Features

* Login/Register system with SQLite (UID generation)
* Realtime one-to-one chat with styled UI
* Theme switching (🌙/☀️) with saved preferences
* Role switching between Controller and Target
* Screen sharing and mouse/keyboard control (coming next)
* Relay server-based centralized communication
* Chat logging and session time tracking

---

## 🗂 Folder Structure (Key)

```
remote_desktop_final/
├── main.py                  # Entry point for client app
├── relay.db                 # SQLite database
├── client/                  # UI and client-side logic
│   ├── ui_login.py
│   ├── ui_register.py
│   ├── ui_controller.py
│   ├── app_controller.py
│   ├── controller_client.py
│   ├── target_client.py
│   ├── theme_manager.py
│   ├── window_manager.py
│   └── widgets/chat_widget.py
├── relay_server/           # Server-side logic
│   ├── server.py
│   ├── database.py
│   ├── logger.py
├── shared/                 # Shared utils & protocol
│   ├── constants.py
│   ├── protocol.py
│   ├── utils.py
├── assets/                 # Icons + stylesheets
│   └── styles/*.qss
```

---

## 🚀 How to Run

### 1️⃣ Start the Relay Server

Open terminal:

```bash
cd remote_desktop_final/relay_server
python server.py
```

### 2️⃣ Start Client #1 (Ali, for example)

In another terminal:

```bash
cd remote_desktop_final
python main.py
```

Login as user: `ali`

### 3️⃣ Start Client #2 (Mia, for example)

In third terminal or another machine:

```bash
cd remote_desktop_final
python main.py
```

Login as user: `mia`

## ✅ Usage

* Use UID of second client to connect
* Send messages → they appear in modern chat bubbles
* Switch role to test both view/controller modes
* Change theme via 🌙/☀️ toggle → all UI adapts

---

## 🔜 Coming Next

* Image-based screen sharing (Target → Controller)
* Input permission and control (Controller → Target)
* Token-based backend API integration
* Full session log viewer & admin dashboard

---

## 📦 Requirements

* Python 3.10+
* PyQt5
* Use `pip install -r requirements.txt` to install dependencies

---

## 🧪 Tests

Run unit tests:

```bash
cd remote_desktop_final\pytest
```

---

## 💬 Contact

For help or suggestions, contact the SCU Remote Team. 