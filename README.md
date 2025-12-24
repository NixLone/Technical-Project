![Status](https://img.shields.io/badge/status-Coming%20Soon-brightgreen?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)
# ToolCards Project

### 📌 Project Description
ToolCards is a desktop application designed to simplify the process of creating and managing tool cards for manufacturing and engineering tasks.
The system allows you to:
- 📊 Store tool data in a local database (SQLite)
- 🖼️ Attach images and technical drawings
- 🔎 Search and filter tools by type and parameters
- 📑 Export cards to Excel, PDF, or PNG

This project is built with Python and aims to automate repetitive tasks, saving valuable time for engineers and technicians.

---

### 🚀 Features
- Easy-to-use GUI
- Support for multiple tool types (drills, end mills, holders)
- Automatic recognition of parameters from images (via OCR)
- Offline support — works without internet connection

---

### ⚙️ Technologies Used
- Python 3.12
- SQLite
- Tkinter / PyQt (for GUI)
- OpenCV + Tesseract (for OCR)
- Pandas, Pillow, ReportLab

---

### 📥 Installation (GitHub release)
1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-org>/Technical-Project.git
   cd Technical-Project
   ```
2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *The OCR flow also requires the system Tesseract binary. On Ubuntu: `sudo apt install tesseract-ocr`.*
4. **Initialize the SQLite database:**
   ```bash
   python tool_manager.py init-db --seed
   ```
5. **Run commands or start the GUI (desktop only):**
   ```bash
   python tool_manager.py --help
   python tool_manager.py gui
   ```

---

## 🧰 Running without a desktop (cloud / Telegram bot)
The `tool_manager.py` module now exposes a CLI and safe database helpers that can be reused from a bot handler or a headless service.

1. **Install dependencies** (OCR is optional):
   ```bash
   pip install opencv-python pytesseract pillow
   ```
2. **Initialize the database** (with optional demo data):
   ```bash
   python tool_manager.py init-db --seed
   ```
3. **Import data from a drawing image using OCR**:
   ```bash
   python tool_manager.py import-drawing path/to/image.png --tool-type drill
   ```
4. **Search existing tools**:
   ```bash
   python tool_manager.py search DGC-
   ```
5. **Attach an image to an existing tool**:
   ```bash
   python tool_manager.py add-image DGC-3143D2.5 path/to/photo.jpg
   ```

### Integrating with Telegram
The database (`ToolDatabase`) and OCR (`OCRService`) classes can be imported and called from a Telegram bot handler. Keep `TOOL_DB_PATH` set to a writable location in your hosting environment so multiple bot workers share the same data file.


# ToolCards Project (RU)

### 📌 Описание проекта
ToolCards — это настольное приложение, упрощающее процесс создания и управления карточками инструмента для производственных и инженерных задач.
Система позволяет:
- 📊 Хранить данные об инструменте в локальной базе (SQLite)
- 🖼️ Прикреплять изображения и чертежи
- 🔎 Искать и фильтровать инструменты по типу и параметрам
- 📑 Экспортировать карточки в Excel, PDF или PNG

Проект создан на Python и помогает автоматизировать рутинные процессы, экономя время инженеров и техников.

### 🚀Возможности
- Удобный графический интерфейс
- Поддержка разных типов инструмента (сверла, фрезы, державки)
- Автоматическое распознавание параметров с изображений (OCR)
- Полностью автономная работа без интернета

### ⚙️ Технологии
- Python 3.12
- SQLite
- Tkinter / PyQt (GUI)
- OpenCV + Tesseract (OCR)
- Pandas, Pillow, ReportLab

### 📥 Установка
1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/<your-org>/Technical-Project.git
   cd Technical-Project
   ```
2. **Создайте виртуальное окружение (рекомендуется):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   ```
3. **Установите зависимости:**
   ```bash
   pip install -r requirements.txt
   ```
   *Для OCR потребуется системный бинарник Tesseract. В Ubuntu: `sudo apt install tesseract-ocr`.*
4. **Инициализируйте базу данных SQLite:**
   ```bash
   python tool_manager.py init-db --seed
   ```
5. **Запускайте команды или GUI (только на рабочем столе):**
   ```bash
   python tool_manager.py --help
   python tool_manager.py gui
   ```
