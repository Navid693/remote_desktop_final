# 🖥️ SCU Remote Desktop

## 📚 Language / زبان

* [🇬🇧 English Version](#english-version)
* [🇮🇷 نسخه فارسی](#نسخه-فارسی)

---

## 🇬🇧 English Version

SCU Remote Desktop is a cross-platform desktop-sharing and remote-control application inspired by tools like AnyDesk. It allows users to share their screen, control remote machines, and communicate via chat, all routed through a central relay server. While designed to be cross-platform, some features—like high-fidelity screen capture and remote input control—have better support or specific implementations on Windows.

---

## 🌟 Project Overview

This application provides a feature-rich remote desktop experience. Users can register and log in, then act as either a **Controller** (to view and control another machine) or a **Target** (to share their screen and be controlled). All communication—chat, screen data, and input events—is relayed through a Python-based central server. A SQLite database manages users and sessions, while the user interface is built with PyQt5 and supports theme switching.

---

## ✅ Key Features

* **User Authentication:** Secure login and registration with UID generation and password hashing (SQLite backend).
* **Role-Based Access:** Easily switch between Controller and Target roles.
* **Real-Time Chat:** One-on-one chat with message bubbles and timestamps.
* **Theme Switching:** Toggle between dark and light themes with saved preferences.
* **Relay Server:** Central server for brokering and relaying connections.
* **Session Management:** Track and manage active Controller–Target sessions.
* **Comprehensive Logging:** Store logs for client and server actions.
* **Admin Panel:** Manage users and view system logs.
* **Screen Sharing:** Real-time streaming of the target’s screen.
* **Remote Input Control:** Control mouse and keyboard actions on the target machine.
* **Permission System:** Target users can approve or deny screen view/control requests.
* **Screenshot Tool:** Capture screenshots from remote or local devices.

---

## 🛠️ Technology Stack

* **Language:** Python 3.10+
* **GUI Framework:** PyQt5
* **Networking:** Python's `socket` and `socketserver`
* **Database:** SQLite
* **Image Handling:** Pillow (PIL)
* **Input Control:** pynput
* **Styling:** Qt Style Sheets (QSS)

---

## 🗂 Folder Structure (Simplified)

```plaintext
remote_desktop_final/
├── client/
├── relay_server/
├── shared/
├── assets/
├── Tests/
├── main.py
├── requirements.txt
└── README.md
```

---

## ⚙️ Prerequisites

* Python 3.10 or higher
* pip (Python package manager)

---

## 🚀 Setup and Installation

```bash
# Clone the repository
git clone <repository-url>
cd remote_desktop_final

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

---

## 🏁 How to Run

```bash
# Start the Relay Server
cd relay_server
python server.py

# Run Client Application (new terminal)
cd ..
python main.py
```

Repeat for both Controller and Target roles (on same or separate machines).

---

## 🕹️ Usage Highlights

* Log in or register as a user (admin credentials: `admin` / `admin`)
* Choose your role: Controller or Target
* Enter the Target UID to connect
* Request permission for screen view/control
* Use the chat panel and toolbar features (screenshot, theme, record, etc.)

---

## 🧪 Tests and Development Tools

```bash
# Run all tests
pytest

# Format and lint code
black .
mypy .
flake8
```

---

## 🚧 Roadmap

* Improve screen streaming performance
* File transfer support
* Multi-monitor functionality
* TLS encryption
* Clipboard sync between clients
* CLI-based client

---

## 📜 License

This project is licensed under the **MIT License**.
See the [LICENSE](LICENSE) file for more information.

---

## 📨 Contact

If you have questions, suggestions, or would like to contribute:

* 📧 Email: [navidshiekhzadeh1@gmail.com](mailto:navidshiekhzadeh1@gmail.com)
* 💬 Telegram: [@navid693](https://t.me/navid693)

---

## 🇮🇷 نسخه فارسی

SCU Remote Desktop یک نرم‌افزار چندسکویی برای اشتراک‌گذاری دسکتاپ و کنترل از راه دور است که با الهام از ابزارهایی مانند AnyDesk ساخته شده است. این برنامه به کاربران امکان می‌دهد صفحه نمایش خود را به اشتراک بگذارند، دستگاه‌های دیگر را کنترل کنند و از طریق چت با یکدیگر ارتباط برقرار کنند. تمام ارتباطات از طریق یک سرور مرکزی هدایت می‌شود.

---

### 🎯 هدف پروژه

این برنامه تجربه‌ای کامل و قابل‌اعتماد از ریموت دسکتاپ را فراهم می‌کند. کاربران می‌توانند به عنوان Controller (کنترل‌کننده) یا Target (کنترل‌شونده) وارد سیستم شوند. داده‌های تصویر، پیام‌ها و فرمان‌های ورودی از طریق سرور relay منتقل می‌شوند. رابط گرافیکی با PyQt5 پیاده‌سازی شده و امکان تغییر تم نیز دارد.

---

### ✅ ویژگی‌ها

* احراز هویت ایمن با پایگاه داده SQLite
* انتخاب پویا بین نقش کنترل‌کننده و کنترل‌شونده
* چت زنده با رابط کاربری زیبا
* قابلیت تغییر تم (روشن/تاریک) با ذخیره تنظیمات
* سرور مرکزی برای برقراری اتصال بین کلاینت‌ها
* مدیریت نشست‌ها و ثبت فعالیت‌ها
* پنل مدیریت کاربران برای مدیر سیستم
* اشتراک‌گذاری زنده صفحه نمایش
* کنترل از راه دور موس و کیبورد (با pynput)
* سیستم درخواست مجوز برای مشاهده یا کنترل
* امکان گرفتن اسکرین‌شات از سیستم راه دور یا محلی

---

### ⚙️ پیش‌نیازها

* پایتون نسخه ۳.۱۰ یا بالاتر
* ابزار pip برای نصب کتابخانه‌ها

---

### 🚀 نصب و اجرا

```bash
1. کلون کردن مخزن
2. ایجاد محیط مجازی
3. نصب وابستگی‌ها
4. اجرای سرور relay و سپس اجرای کلاینت در دو نقش مختلف
```

---

### 🧪 تست و توسعه

* اجرای تست‌ها با دستور `pytest`
* ابزارهای توسعه: `black`, `mypy`, `flake8`

---

### 🧭 نقشه راه

* بهینه‌سازی نمایش تصویر
* پشتیبانی از انتقال فایل
* پشتیبانی از چند نمایشگر
* رمزنگاری ارتباطات با TLS
* همگام‌سازی کلیپ‌بورد
* طراحی نسخه خط فرمان (CLI)

---

### 📬 ارتباط با ما

* ایمیل: [navidshiekhzadeh1@gmail.com](mailto:navidshiekhzadeh1@gmail.com)
* تلگرام: [@navid693](https://t.me/navid693)

---
