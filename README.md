![Status](https://img.shields.io/badge/status-Coming%20Soon-brightgreen?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)
# ToolCards Project

### 📌 Project Description
ToolCards is a desktop application designed to simplify the process of creating and managing tool cards for manufacturing and engineering tasks.
The system allows you to:
- 📊 Store tool data in a local database (SQLite)
- 🖼️ Attach images and technical drawings
- 🔎 Search and filter tools by category and parameters
- 🧾 Generate a cutout image with parameters for chat or bot replies

This project is built with Python and aims to automate repetitive tasks, saving valuable time for engineers and technicians.

---

### 🚀 Features
- Easy-to-use GUI
- Categories managed by admins (mills, drill bodies, drills, inserts, etc.)
- OCR recognition of tool tables with configurable training profiles
- Offline support — works without internet connection

---

### ⚙️ Technologies Used
- Python 3.12
- SQLite
- Tkinter / PyQt (for GUI)
- OpenCV + Tesseract (for OCR)
- Pillow

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
3. **Add categories and tools** (admin flow):
   ```bash
   python tool_manager.py add-category "Фреза"
   python tool_manager.py add-tool WTE-4F1035 "Фреза" "D=10;L=100;l1=50"
   ```
4. **Train OCR settings per category**:
   ```bash
   python tool_manager.py train-ocr "Фреза" --size-keys D,L,l1 --threshold 170 --psm 6
   ```
5. **Import data from a drawing image using OCR**:
   ```bash
   python tool_manager.py import-drawing path/to/image.png --category "Фреза"
   ```
6. **Search existing tools**:
   ```bash
   python tool_manager.py search WTE-
   ```
7. **Attach an image to an existing tool**:
   ```bash
   python tool_manager.py add-image WTE-4F1035 path/to/photo.jpg
   ```
8. **Create a cutout for a chat reply**:
   ```bash
   python tool_manager.py make-cutout WTE-4F1035 output/cutout.png
   ```

### Integrating with Telegram
The database (`ToolDatabase`) and OCR (`OCRService`) classes can be imported and called from a Telegram bot handler. Keep `TOOL_DB_PATH` set to a writable location in your hosting environment so multiple bot workers share the same data file.


# ToolCards Project (RU)

### 📌 Описание проекта
ToolCards — это настольное приложение, упрощающее процесс создания и управления карточками инструмента для производственных и инженерных задач.
Система позволяет:
- 📊 Хранить данные об инструменте в локальной базе (SQLite)
- 🖼️ Прикреплять изображения и чертежи
- 🔎 Искать и фильтровать инструменты по категориям и параметрам
- 🧾 Формировать «вырезку» с параметрами для отправки в чате или боте

Проект создан на Python и помогает автоматизировать рутинные процессы, экономя время инженеров и техников.

### 🚀 Возможности
- Удобный графический интерфейс
- Категории создаются администратором (фрезы, корпуса, сверла, пластины и т.д.)
- OCR автоматически читает таблицы и достает название + размеры
- Профили обучения OCR настраиваются через меню «Настройки OCR»
- Полностью автономная работа без интернета

### ⚙️ Технологии
- Python 3.12
- SQLite
- Tkinter / PyQt (GUI)
- OpenCV + Tesseract (OCR)
- Pillow

---

## 📥 Установка
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

---

## 🧭 Инструкция администратора (категории + обучение OCR)
### 1) Создать категории
Категории нужны, чтобы OCR правильно привязывал инструменты к разделам («Фреза», «Сверло» и т.д.).

**Через GUI:**
1. Откройте вкладку **«📂 Категории»**.
2. Введите название и описание.
3. Нажмите **«Добавить категорию»**.

**Через CLI:**
```bash
python tool_manager.py add-category "Фреза" --description "Концевые фрезы"
```

### 2) Добавить инструмент вручную
**Через GUI:**
1. Вкладка **«➕ Добавить инструмент»**.
2. Укажите код/название, категорию, параметры.
3. Нажмите **«Сохранить инструмент»**.

**Через CLI:**
```bash
python tool_manager.py add-tool WTE-4F1035 "Фреза" "D=10;L=100;l1=50"
```

### 3) Обучить OCR (интуитивно через настройки)
**Через GUI:**
1. Вкладка **«⚙️ Настройки OCR»**.
2. Выберите категорию.
3. Заполните:
   - **Шаблон имени (regex)** — если нужно вытаскивать название сложнее, чем первый токен.
   - **Ключи размеров** — список размеров в таблице: `D,L,l1,DC`.
   - **Порог** и **PSM** — влияют на качество распознавания.
4. Нажмите **«Сохранить настройки OCR»**.

**Через CLI:**
```bash
python tool_manager.py train-ocr "Фреза" --size-keys D,L,l1 --threshold 170 --psm 6
```

### 4) Импортировать таблицу через OCR
**Через GUI:** вкладка **«📥 Импорт чертежа»**, выберите категорию и изображение.

**Через CLI:**
```bash
python tool_manager.py import-drawing path/to/image.png --category "Фреза"
```

---

## 🙋 Инструкция пользователя (поиск и «вырезка»)
### 1) Найти инструмент
**Через GUI:** вкладка **«🔍 Поиск инструмента»**, введите часть названия.

**Через CLI:**
```bash
python tool_manager.py search WTE-
```

### 2) Добавить изображение инструмента
Изображение нужно, чтобы «вырезка» совпадала с названием и категорией.

**Через GUI:** вкладка **«🖼 Добавить картинку»**.

**Через CLI:**
```bash
python tool_manager.py add-image WTE-4F1035 path/to/photo.jpg
```

### 3) Создать «вырезку» для чата
Если пользователь пишет в чате «Сделай вырезку WTE-4F1035», бот вызывает:
```bash
python tool_manager.py make-cutout WTE-4F1035 output/cutout.png
```
На выходе получается картинка с изображением инструмента и параметрами из базы.

---

## 🤖 Интеграция с Telegram
Бот хранит базу SQLite в общем каталоге. Команды можно вызывать напрямую из обработчиков.
Переменная `TOOL_DB_PATH` задает путь к базе данных.
