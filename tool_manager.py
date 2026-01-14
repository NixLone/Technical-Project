"""
ToolCards management utilities.

This module provides a CLI-friendly interface for managing the SQLite
catalog, plus an optional Tkinter GUI for desktop use. It is safe to run
in headless or containerized environments (GUI is enabled only when the
dependencies are present).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("TOOL_DB_PATH", "test_tools.db"))

try:  # Optional OCR stack
    import cv2
    import pytesseract

    OCR_AVAILABLE = True
except Exception as exc:  # pragma: no cover - optional dependency
    LOGGER.warning("OCR stack unavailable: %s", exc)
    OCR_AVAILABLE = False

try:  # Optional GUI stack
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    GUI_AVAILABLE = True
except Exception as exc:  # pragma: no cover - optional dependency
    LOGGER.warning("Tkinter stack unavailable: %s", exc)
    GUI_AVAILABLE = False
    tk = filedialog = messagebox = ttk = None

try:  # Optional imaging stack for cutouts
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except Exception as exc:  # pragma: no cover - optional dependency
    LOGGER.warning("Pillow stack unavailable: %s", exc)
    PIL_AVAILABLE = False
    Image = ImageDraw = ImageFont = None


@dataclass
class OCRProfile:
    category_id: int
    category_name: str
    name_pattern: str | None = None
    size_keys: List[str] | None = None
    threshold: int = 180
    invert: bool = True
    psm: int = 6
    notes: str | None = None

    def to_json(self) -> str:
        payload = {
            "name_pattern": self.name_pattern,
            "size_keys": self.size_keys or [],
            "threshold": self.threshold,
            "invert": self.invert,
            "psm": self.psm,
            "notes": self.notes,
        }
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def from_row(cls, category_id: int, category_name: str, config_json: str | None) -> "OCRProfile":
        if not config_json:
            return cls(category_id=category_id, category_name=category_name)
        data = json.loads(config_json)
        return cls(
            category_id=category_id,
            category_name=category_name,
            name_pattern=data.get("name_pattern"),
            size_keys=list(data.get("size_keys", [])),
            threshold=int(data.get("threshold", 180)),
            invert=bool(data.get("invert", True)),
            psm=int(data.get("psm", 6)),
            notes=data.get("notes"),
        )


class ToolDatabase:
    """SQLite wrapper with basic validation and safe defaults."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)

    def initialize(self, seed: bool = False) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_code TEXT NOT NULL,
                    category_id INTEGER NOT NULL,
                    params TEXT,
                    image_path TEXT,
                    FOREIGN KEY (category_id) REFERENCES categories (id)
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER UNIQUE NOT NULL,
                    config_json TEXT,
                    FOREIGN KEY (category_id) REFERENCES categories (id)
                );
                """
            )
            if seed and not self._has_existing_data(cursor):
                seed_categories = [
                    ("Фреза", "Концевые фрезы и вариации"),
                    ("Корпус фрезы", "Державки и корпуса"),
                    ("Сверло", "Сверла и сверлильный инструмент"),
                    ("Пластина", "Сменные пластины"),
                ]
                cursor.executemany(
                    "INSERT INTO categories (name, description) VALUES (?, ?)",
                    seed_categories,
                )
                categories = self._category_lookup(cursor)
                cursor.executemany(
                    """
                    INSERT INTO tools (tool_code, category_id, params, image_path)
                    VALUES (?,?,?,?)
                    """,
                    [
                        ("DGC-3143D2.5", categories["Сверло"], "D=2.5;L=57;l1=30", None),
                        ("WTE-4F1035", categories["Фреза"], "D=10;L=100;l1=50;l2=20;d=8", None),
                        (
                            "WUD-C25-3D19-SP05-63",
                            categories["Корпус фрезы"],
                            "DC=25;L=133;L_work=75;l1=40",
                            None,
                        ),
                    ],
                )
                conn.commit()

    def _has_existing_data(self, cursor: sqlite3.Cursor) -> bool:
        cursor.execute("SELECT COUNT(*) FROM categories")
        count = cursor.fetchone()[0]
        return bool(count)

    def _category_lookup(self, cursor: sqlite3.Cursor) -> dict[str, int]:
        cursor.execute("SELECT id, name FROM categories")
        return {name: category_id for category_id, name in cursor.fetchall()}

    def list_categories(self) -> List[Tuple[int, str, str | None]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, description FROM categories ORDER BY name")
            return cursor.fetchall()

    def add_category(self, name: str, description: str | None = None) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)",
                (name, description),
            )
            conn.commit()
            cursor.execute("SELECT id FROM categories WHERE name=?", (name,))
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("Failed to create category")
            return int(row[0])

    def get_category(self, name: str) -> Tuple[int, str, str | None]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, description FROM categories WHERE name=?",
                (name.strip(),),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Unknown category: {name}")
            return row

    def insert_tools(self, rows: Iterable[Tuple[str, str, str, str | None]]) -> None:
        safe_rows = [self._sanitize_row(row) for row in rows]
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO tools (tool_code, category_id, params, image_path)
                VALUES (?, ?, ?, ?)
                """,
                safe_rows,
            )
            conn.commit()

    def add_tool(
        self,
        tool_code: str,
        category_name: str,
        params: str,
        image_path: str | None = None,
    ) -> None:
        rows = [(tool_code, category_name, params, image_path)]
        self.insert_tools(rows)

    def add_image(self, tool_code: str, image_path: str) -> None:
        tool_code = tool_code.strip()
        image_path = str(Path(image_path).expanduser().resolve())
        if not tool_code:
            raise ValueError("Tool code cannot be empty")
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tools SET image_path=? WHERE tool_code=?",
                (image_path, tool_code),
            )
            conn.commit()

    def search_tools(self, query: str) -> List[Tuple[int, str, str, str, str | None]]:
        query = query.strip()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tools.id, tools.tool_code, categories.name, tools.params, tools.image_path
                FROM tools
                JOIN categories ON categories.id = tools.category_id
                WHERE tools.tool_code LIKE ?
                """,
                (f"%{query}%",),
            )
            return cursor.fetchall()

    def get_tool_by_code(self, tool_code: str) -> Tuple[int, str, str, str, str | None]:
        tool_code = tool_code.strip()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tools.id, tools.tool_code, categories.name, tools.params, tools.image_path
                FROM tools
                JOIN categories ON categories.id = tools.category_id
                WHERE tools.tool_code = ?
                """,
                (tool_code,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Tool not found: {tool_code}")
            return row

    def save_ocr_profile(self, profile: OCRProfile) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO ocr_profiles (category_id, config_json)
                VALUES (?, ?)
                ON CONFLICT(category_id) DO UPDATE SET config_json=excluded.config_json
                """,
                (profile.category_id, profile.to_json()),
            )
            conn.commit()

    def get_ocr_profile(self, category_name: str) -> OCRProfile:
        category_id, name, _ = self.get_category(category_name)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT config_json FROM ocr_profiles WHERE category_id=?",
                (category_id,),
            )
            row = cursor.fetchone()
            config_json = row[0] if row else None
            return OCRProfile.from_row(category_id, name, config_json)

    def _sanitize_row(self, row: Sequence[str | None]) -> Tuple[str, int, str, str | None]:
        try:
            tool_code, category_name, params, image_path = row
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("Row must have exactly four elements") from exc

        tool_code = str(tool_code).strip()
        category_name = str(category_name).strip()
        params = str(params).strip()
        image_path = str(image_path) if image_path is not None else None

        if not tool_code:
            raise ValueError("Tool code cannot be empty")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM categories WHERE name=?",
                (category_name,),
            )
            category = cursor.fetchone()
            if not category:
                raise ValueError(f"Unknown category: {category_name}")
            category_id = int(category[0])

        return tool_code, category_id, params, image_path


class OCRService:
    def __init__(self, db: ToolDatabase):
        self.db = db

    def read_drawing(self, image_path: str, category_name: str) -> List[Tuple[str, str, str, None]]:
        if not OCR_AVAILABLE:
            raise RuntimeError("OCR stack is not installed. Install opencv-python and pytesseract.")

        image_path_obj = Path(image_path).expanduser().resolve()
        if not image_path_obj.exists():
            raise FileNotFoundError(f"Image not found: {image_path_obj}")

        profile = self.db.get_ocr_profile(category_name)

        img = cv2.imread(str(image_path_obj))
        if img is None:
            raise ValueError(f"Cannot read image: {image_path_obj}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        threshold_type = cv2.THRESH_BINARY_INV if profile.invert else cv2.THRESH_BINARY
        _, thresh = cv2.threshold(gray, profile.threshold, 255, threshold_type + cv2.THRESH_OTSU)

        custom_config = f"--oem 3 --psm {profile.psm}"
        text = pytesseract.image_to_string(thresh, config=custom_config)

        rows: List[Tuple[str, str, str, None]] = []
        size_keys = [key.strip() for key in (profile.size_keys or []) if key.strip()]

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            tool_name = self._extract_tool_name(line, profile.name_pattern)
            params = self._extract_params(line, size_keys)
            if tool_name and params:
                rows.append((tool_name, category_name, params, None))
            elif tool_name:
                rows.append((tool_name, category_name, line, None))
        return rows

    def _extract_tool_name(self, line: str, pattern: str | None) -> str | None:
        if pattern:
            match = re.search(pattern, line)
            if match:
                return match.group(0).strip()
        tokens = line.split()
        return tokens[0].strip() if tokens else None

    def _extract_params(self, line: str, size_keys: List[str]) -> str:
        params: List[str] = []
        for key in size_keys:
            regex = re.compile(rf"{re.escape(key)}\s*[:=]?\s*([0-9]+[.,]?[0-9]*)", re.IGNORECASE)
            match = regex.search(line)
            if match:
                value = match.group(1).replace(",", ".")
                params.append(f"{key}={value}")
        return ";".join(params)

    def import_from_image(self, image_path: str, category_name: str) -> int:
        rows = self.read_drawing(image_path, category_name)
        if rows:
            self.db.insert_tools(rows)
        return len(rows)


class ToolCardGenerator:
    def __init__(self, db: ToolDatabase):
        self.db = db

    def create_cutout(self, tool_code: str, output_path: str) -> str:
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow is not installed. Install pillow to generate cutouts.")

        tool_id, code, category, params, image_path = self.db.get_tool_by_code(tool_code)
        if not image_path:
            raise ValueError("Tool has no image attached. Add one with add-image.")

        image = Image.open(image_path)
        width, height = image.size
        canvas = Image.new("RGB", (width, height + 160), "white")
        canvas.paste(image, (0, 0))

        draw = ImageDraw.Draw(canvas)
        title = f"{category}: {code}"
        text = params or ""

        font = ImageFont.load_default()
        draw.text((10, height + 10), title, fill="black", font=font)
        draw.text((10, height + 40), text, fill="black", font=font)

        output_path_obj = Path(output_path).expanduser().resolve()
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path_obj)

        return str(output_path_obj)


class ToolApp:
    """Tkinter GUI wrapper. Intended for desktop environments only."""

    def __init__(self, root: tk.Tk, db: ToolDatabase, ocr: OCRService | None):
        self.db = db
        self.ocr = ocr
        self.root = root
        self.root.title("Tool Card Generator")
        self.root.geometry("1100x650")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        self.frame1 = ttk.Frame(self.notebook)
        self.notebook.add(self.frame1, text="📥 Импорт чертежа")

        self.category_var = tk.StringVar(value="")
        self.category_combo = ttk.Combobox(self.frame1, textvariable=self.category_var, width=40)
        self.category_combo.pack(pady=6)

        self.btn_load = ttk.Button(
            self.frame1,
            text="Загрузить изображение и распознать",
            command=self.load_image,
        )
        self.btn_load.pack(pady=10)

        self.label_result = tk.Label(self.frame1, text="Результаты OCR появятся здесь")
        self.label_result.pack()

        self.frame2 = ttk.Frame(self.notebook)
        self.notebook.add(self.frame2, text="🔍 Поиск инструмента")

        self.entry_search = ttk.Entry(self.frame2, width=40)
        self.entry_search.pack(pady=10)
        self.btn_search = ttk.Button(self.frame2, text="Найти", command=self.search_tool)
        self.btn_search.pack()

        self.tree = ttk.Treeview(
            self.frame2, columns=("id", "tool_code", "category", "params", "image"), show="headings"
        )
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col)
        self.tree.pack(fill="both", expand=True)

        self.frame3 = ttk.Frame(self.notebook)
        self.notebook.add(self.frame3, text="🖼 Добавить картинку")

        self.entry_code = ttk.Entry(self.frame3, width=40)
        self.entry_code.pack(pady=10)
        self.btn_add_img = ttk.Button(
            self.frame3, text="Выбрать картинку", command=self.add_image_to_tool
        )
        self.btn_add_img.pack()

        self.frame4 = ttk.Frame(self.notebook)
        self.notebook.add(self.frame4, text="➕ Добавить инструмент")

        self.entry_new_code = ttk.Entry(self.frame4, width=40)
        self.entry_new_code.pack(pady=6)
        self.entry_new_code.insert(0, "Код/название инструмента")

        self.new_category_var = tk.StringVar(value="")
        self.new_category_combo = ttk.Combobox(
            self.frame4, textvariable=self.new_category_var, width=40
        )
        self.new_category_combo.pack(pady=6)

        self.entry_new_params = ttk.Entry(self.frame4, width=60)
        self.entry_new_params.pack(pady=6)
        self.entry_new_params.insert(0, "Параметры (например, D=10;L=50)")

        self.btn_add_tool = ttk.Button(
            self.frame4, text="Сохранить инструмент", command=self.add_tool
        )
        self.btn_add_tool.pack(pady=10)

        self.frame5 = ttk.Frame(self.notebook)
        self.notebook.add(self.frame5, text="📂 Категории")

        self.entry_category_name = ttk.Entry(self.frame5, width=40)
        self.entry_category_name.pack(pady=6)
        self.entry_category_name.insert(0, "Название категории")

        self.entry_category_desc = ttk.Entry(self.frame5, width=60)
        self.entry_category_desc.pack(pady=6)
        self.entry_category_desc.insert(0, "Описание (необязательно)")

        self.btn_add_category = ttk.Button(
            self.frame5, text="Добавить категорию", command=self.add_category
        )
        self.btn_add_category.pack(pady=6)

        self.category_list = tk.Listbox(self.frame5, width=80, height=10)
        self.category_list.pack(pady=10)

        self.frame6 = ttk.Frame(self.notebook)
        self.notebook.add(self.frame6, text="⚙️ Настройки OCR")

        self.ocr_category_var = tk.StringVar(value="")
        self.ocr_category_combo = ttk.Combobox(
            self.frame6, textvariable=self.ocr_category_var, width=40
        )
        self.ocr_category_combo.pack(pady=6)

        self.entry_name_pattern = ttk.Entry(self.frame6, width=60)
        self.entry_name_pattern.pack(pady=4)
        self.entry_name_pattern.insert(0, "Шаблон имени (regex), можно оставить пустым")

        self.entry_size_keys = ttk.Entry(self.frame6, width=60)
        self.entry_size_keys.pack(pady=4)
        self.entry_size_keys.insert(0, "Ключи размеров через запятую, например: D,L,l1")

        self.entry_threshold = ttk.Entry(self.frame6, width=20)
        self.entry_threshold.pack(pady=4)
        self.entry_threshold.insert(0, "180")

        self.invert_var = tk.BooleanVar(value=True)
        self.check_invert = ttk.Checkbutton(
            self.frame6, text="Инвертировать изображение", variable=self.invert_var
        )
        self.check_invert.pack(pady=4)

        self.entry_psm = ttk.Entry(self.frame6, width=20)
        self.entry_psm.pack(pady=4)
        self.entry_psm.insert(0, "6")

        self.entry_notes = ttk.Entry(self.frame6, width=60)
        self.entry_notes.pack(pady=4)
        self.entry_notes.insert(0, "Примечания для обучения (необязательно)")

        self.btn_save_profile = ttk.Button(
            self.frame6, text="Сохранить настройки OCR", command=self.save_ocr_profile
        )
        self.btn_save_profile.pack(pady=10)

        self.refresh_categories()

    def refresh_categories(self) -> None:
        categories = self.db.list_categories()
        names = [name for _, name, _ in categories]
        for combo in (self.category_combo, self.new_category_combo, self.ocr_category_combo):
            combo["values"] = names
            if not combo.get() and names:
                combo.set(names[0])

        self.category_list.delete(0, tk.END)
        for _, name, description in categories:
            suffix = f" — {description}" if description else ""
            self.category_list.insert(tk.END, f"{name}{suffix}")

    def load_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not path:
            return
        if not self.ocr:
            self.label_result.config(text="OCR не доступен в данной среде")
            return
        category = self.category_combo.get()
        if not category:
            messagebox.showerror("Ошибка", "Выберите категорию")
            return
        try:
            imported = self.ocr.import_from_image(path, category)
        except Exception as exc:  # pragma: no cover - UI layer
            messagebox.showerror("Ошибка", str(exc))
            return

        if imported:
            self.label_result.config(text=f"Успешно импортировано {imported} строк")
        else:
            self.label_result.config(text="Не удалось распознать таблицу")

    def search_tool(self) -> None:
        query = self.entry_search.get()
        rows = self.db.search_tools(query)
        for row in self.tree.get_children():
            self.tree.delete(row)
        for row in rows:
            self.tree.insert("", tk.END, values=row)

    def add_image_to_tool(self) -> None:
        code = self.entry_code.get()
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not code or not path:
            messagebox.showerror("Ошибка", "Введите код и выберите изображение")
            return
        try:
            self.db.add_image(code, path)
        except Exception as exc:  # pragma: no cover - UI layer
            messagebox.showerror("Ошибка", str(exc))
            return
        messagebox.showinfo("Успех", f"Изображение добавлено для {code}")

    def add_tool(self) -> None:
        code = self.entry_new_code.get().strip()
        category = self.new_category_combo.get().strip()
        params = self.entry_new_params.get().strip()
        if not code or not category:
            messagebox.showerror("Ошибка", "Введите код и выберите категорию")
            return
        try:
            self.db.add_tool(code, category, params)
        except Exception as exc:  # pragma: no cover - UI layer
            messagebox.showerror("Ошибка", str(exc))
            return
        messagebox.showinfo("Успех", f"Инструмент {code} добавлен")

    def add_category(self) -> None:
        name = self.entry_category_name.get().strip()
        description = self.entry_category_desc.get().strip() or None
        if not name:
            messagebox.showerror("Ошибка", "Введите название категории")
            return
        try:
            self.db.add_category(name, description)
        except Exception as exc:  # pragma: no cover - UI layer
            messagebox.showerror("Ошибка", str(exc))
            return
        self.refresh_categories()
        messagebox.showinfo("Успех", f"Категория {name} добавлена")

    def save_ocr_profile(self) -> None:
        category = self.ocr_category_combo.get().strip()
        if not category:
            messagebox.showerror("Ошибка", "Выберите категорию")
            return
        name_pattern = self.entry_name_pattern.get().strip()
        size_keys = [key.strip() for key in self.entry_size_keys.get().split(",") if key.strip()]
        try:
            threshold = int(self.entry_threshold.get().strip())
            psm = int(self.entry_psm.get().strip())
        except ValueError:
            messagebox.showerror("Ошибка", "Порог и PSM должны быть числами")
            return
        invert = bool(self.invert_var.get())
        notes = self.entry_notes.get().strip() or None

        try:
            category_id, _, _ = self.db.get_category(category)
            profile = OCRProfile(
                category_id=category_id,
                category_name=category,
                name_pattern=name_pattern or None,
                size_keys=size_keys,
                threshold=threshold,
                invert=invert,
                psm=psm,
                notes=notes,
            )
            self.db.save_ocr_profile(profile)
        except Exception as exc:  # pragma: no cover - UI layer
            messagebox.showerror("Ошибка", str(exc))
            return
        messagebox.showinfo("Успех", "Настройки OCR сохранены")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ToolCards utilities (GUI optional)")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DB_PATH,
        help="Path to SQLite database (default: test_tools.db)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Create database schema")
    init_parser.add_argument("--seed", action="store_true", help="Insert demo records")

    add_category_parser = subparsers.add_parser("add-category", help="Create a new category")
    add_category_parser.add_argument("name", type=str, help="Category name")
    add_category_parser.add_argument("--description", type=str, default=None)

    subparsers.add_parser("list-categories", help="List categories")

    add_tool_parser = subparsers.add_parser("add-tool", help="Add a tool to a category")
    add_tool_parser.add_argument("tool_code", type=str, help="Tool code/name")
    add_tool_parser.add_argument("category", type=str, help="Category name")
    add_tool_parser.add_argument("params", type=str, help="Parameters string")
    add_tool_parser.add_argument("--image", type=str, default=None, help="Optional image path")

    import_parser = subparsers.add_parser(
        "import-drawing", help="Run OCR on an image and persist results"
    )
    import_parser.add_argument("image", type=str, help="Path to the drawing image")
    import_parser.add_argument(
        "--category",
        required=True,
        help="Category name represented in the drawing",
    )

    search_parser = subparsers.add_parser("search", help="Search tools by code fragment")
    search_parser.add_argument("query", type=str, help="Code fragment to look up")

    add_img_parser = subparsers.add_parser("add-image", help="Attach an image to a tool")
    add_img_parser.add_argument("tool_code", type=str, help="Tool code to update")
    add_img_parser.add_argument("image", type=str, help="Image file to attach")

    train_parser = subparsers.add_parser("train-ocr", help="Save OCR settings for a category")
    train_parser.add_argument("category", type=str, help="Category name")
    train_parser.add_argument("--name-pattern", type=str, default=None)
    train_parser.add_argument("--size-keys", type=str, default="")
    train_parser.add_argument("--threshold", type=int, default=180)
    train_parser.add_argument("--invert", action="store_true", help="Invert image")
    train_parser.add_argument("--psm", type=int, default=6)
    train_parser.add_argument("--notes", type=str, default=None)

    cutout_parser = subparsers.add_parser(
        "make-cutout", help="Create a cutout image from tool data"
    )
    cutout_parser.add_argument("tool_code", type=str, help="Tool code to render")
    cutout_parser.add_argument("output", type=str, help="Output file path")

    subparsers.add_parser("gui", help="Launch the Tkinter desktop application")

    return parser


def run_cli(args: argparse.Namespace) -> None:
    db = ToolDatabase(args.db_path)

    if args.command == "init-db":
        db.initialize(seed=args.seed)
        LOGGER.info("Database initialized at %s", db.db_path)
        return

    if args.command == "add-category":
        db.initialize(seed=False)
        category_id = db.add_category(args.name, args.description)
        LOGGER.info("Category created with id %s", category_id)
        return

    if args.command == "list-categories":
        db.initialize(seed=False)
        for row in db.list_categories():
            print(row)
        return

    if args.command == "add-tool":
        db.initialize(seed=False)
        db.add_tool(args.tool_code, args.category, args.params, args.image)
        LOGGER.info("Tool added: %s", args.tool_code)
        return

    if args.command == "import-drawing":
        ocr = OCRService(db)
        imported = ocr.import_from_image(args.image, args.category)
        LOGGER.info("Imported %s row(s) from %s", imported, args.image)
        return

    if args.command == "search":
        db.initialize(seed=False)
        rows = db.search_tools(args.query)
        for row in rows:
            print(row)
        LOGGER.info("Found %s row(s)", len(rows))
        return

    if args.command == "add-image":
        db.add_image(args.tool_code, args.image)
        LOGGER.info("Image attached to %s", args.tool_code)
        return

    if args.command == "train-ocr":
        db.initialize(seed=False)
        category_id, category_name, _ = db.get_category(args.category)
        size_keys = [key.strip() for key in args.size_keys.split(",") if key.strip()]
        profile = OCRProfile(
            category_id=category_id,
            category_name=category_name,
            name_pattern=args.name_pattern,
            size_keys=size_keys,
            threshold=args.threshold,
            invert=args.invert,
            psm=args.psm,
            notes=args.notes,
        )
        db.save_ocr_profile(profile)
        LOGGER.info("OCR profile saved for %s", category_name)
        return

    if args.command == "make-cutout":
        db.initialize(seed=False)
        generator = ToolCardGenerator(db)
        output_path = generator.create_cutout(args.tool_code, args.output)
        LOGGER.info("Cutout created at %s", output_path)
        return

    if args.command == "gui":
        if not GUI_AVAILABLE:
            raise RuntimeError("GUI stack not available in this environment")
        db.initialize(seed=False)
        ocr = OCRService(db) if OCR_AVAILABLE else None
        root = tk.Tk()
        ToolApp(root, db, ocr)
        root.mainloop()
        return

    raise ValueError(f"Unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_cli(args)


if __name__ == "__main__":
    main()
