
# 🖥️ SCU Remote Desktop

## 📚 Language / زبان

* [🇬🇧 English Version](#english-version)
* [🇮🇷 نسخه فارسی](#نسخه-فارسی)

---

## 🇬🇧 English Version

SCU Remote Desktop is a desktop-sharing and remote-control application inspired by tools like AnyDesk. It allows users to share their screen, control remote machines, and communicate via chat, all routed through a central relay server.

---

## 🌟 Project Overview

This application provides a powerful remote desktop experience. Users can register and log in, then act as either a **Controller** (to view and control another machine) or a **Target** (to share their screen and be controlled). All communication—chat, screen data, and input events—is relayed through a Python-based central server. A SQLite database manages users and sessions. The user interface is built with PyQt5 and supports theme switching.

---

## ✅ Key Features

* **Secure Login/Register** with UID and password hashing (SQLite backend)
* **Role Switching:** Controller or Target selection
* **Chat System:** Real-time 1-on-1 messaging
* **Theme Switching:** Light/Dark mode toggle
* **Central Relay Server** for all communications
* **Screen Sharing:** Real-time view of the target screen
* **Mouse & Keyboard Control** over remote machine
* **Permission Handling** before screen/control sharing
* **Screenshot Tool** for remote/local capture
* **Logging:** Server and client logs
* **Admin Panel:** View logs, manage users (CRUD)

---

## 🛠️ Tech Stack

* Python 3.10+
* PyQt5
* socket / socketserver
* SQLite
* Pillow (PIL)
* pynput

---

## 🗂 Folder Structure

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

* Python 3.10+
* pip (Python package manager)

---

## 🚀 Installation & Running Guide

### 🔧 Step 1: Clone the Repository

```bash
git clone https://github.com/Navid693/remote_desktop_final.git
cd remote_desktop_final
```

---

### 🌐 Step 2: Create & Activate Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it (on Windows)
venv\Scripts\activate
```

> 💡 *If you're using macOS/Linux:*
```bash
source venv/bin/activate
```

---

### 📦 Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 🖧 Step 4: Run the Central Relay Server

```bash
python -m relay_server
```

> 🔁 Keep this terminal open to maintain server connection.

---

### 🖥️ Step 5: Run the Client Application (in a New Terminal)

```bash
python main.py
```

---

### ✅ Optional: Run Code Quality & Testing Tools

```bash
pytest
black .
flake8
mypy .
```

---

## 📬 Contact

* 📧 Email: navidshiekhzadeh1@gmail.com
* 💬 Telegram: [@navid693](https://t.me/navid693)

---

## 🇮🇷 نسخه فارسی

SCU Remote Desktop یک برنامه اشتراک‌گذاری دسکتاپ و کنترل از راه دور است که با الهام از AnyDesk طراحی شده. کاربران می‌توانند به‌عنوان Controller یا Target وارد شوند و از طریق سرور مرکزی با هم ارتباط برقرار کنند.

---

### ✅ ویژگی‌ها

* ثبت‌نام و ورود امن با UID و پسورد هش‌شده
* انتخاب نقش بین کنترل‌کننده و کنترل‌شونده
* چت لحظه‌ای بین دو کاربر
* تغییر تم (روشن/تاریک)
* سرور مرکزی برای مدیریت ارتباط‌ها
* اشتراک‌گذاری زنده صفحه نمایش
* کنترل موس و کیبورد سیستم مقابل
* دریافت اجازه برای نمایش یا کنترل
* ابزار اسکرین‌شات از راه دور
* سیستم لاگ‌گیری سمت کلاینت و سرور
* پنل مدیریت برای مشاهده لاگ‌ها و مدیریت کاربران

---

### ⚙️ نصب و اجرا

#### 🔧 مرحله ۱: کلون کردن مخزن

```bash
git clone https://github.com/Navid693/remote_desktop_final.git
cd remote_desktop_final
```

---

#### 🌐 مرحله ۲: ساخت و فعال‌سازی محیط مجازی (venv)

```bash
python -m venv venv
venv\Scripts\activate
```

> 💡 *اگر از macOS یا Linux استفاده می‌کنید:*
```bash
source venv/bin/activate
```

---

#### 📦 مرحله ۳: نصب وابستگی‌ها

```bash
pip install -r requirements.txt
```

---

#### 🖧 مرحله ۴: اجرای سرور مرکزی (Relay Server)

```bash
python -m relay_server
```

> ⚠️ این ترمینال باید باز بماند تا ارتباط برقرار بماند.

---

#### 🖥️ مرحله ۵: اجرای کلاینت در ترمینال جدید

```bash
python main.py
```

---

#### ✅ تست و بررسی کیفیت کد (اختیاری)

```bash
pytest
black .
flake8
mypy .
```

---

### 📬 ارتباط

* ایمیل: navidshiekhzadeh1@gmail.com
* تلگرام: [@navid693](https://t.me/navid693)
