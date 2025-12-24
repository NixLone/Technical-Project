"""
ToolCards management utilities.

This module provides a CLI-friendly interface for managing the SQLite
catalog, plus an optional Tkinter GUI for desktop use. It is safe to run
in headless or containerized environments (GUI is enabled only when the
dependencies are present).
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("TOOL_DB_PATH", "test_tools.db"))
ALLOWED_TOOL_TYPES = {"drill", "endmill", "drill_body"}

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
                CREATE TABLE IF NOT EXISTS tools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_code TEXT,
                    tool_type TEXT,
                    params TEXT,
                    image_path TEXT
                );
                """
            )
            if seed and not self._has_existing_data(cursor):
                cursor.executemany(
                    """
                    INSERT INTO tools (tool_code, tool_type, params, image_path)
                    VALUES (?,?,?,?)
                    """,
                    [
                        ("DGC-3143D2.5", "drill", "D=2.5;L=57;l1=30", None),
                        ("WTE-4F1035", "endmill", "D=10;L=100;l1=50;l2=20;d=8", None),
                        (
                            "WUD-C25-3D19-SP05-63",
                            "drill_body",
                            "DC=25;L=133;L_work=75;l1=40",
                            None,
                        ),
                    ],
                )
                conn.commit()

    def _has_existing_data(self, cursor: sqlite3.Cursor) -> bool:
        cursor.execute("SELECT COUNT(*) FROM tools")
        count = cursor.fetchone()[0]
        return bool(count)

    def insert_tools(self, rows: Iterable[Tuple[str, str, str, str | None]]) -> None:
        safe_rows = [self._sanitize_row(row) for row in rows]
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO tools (tool_code, tool_type, params, image_path)
                VALUES (?, ?, ?, ?)
                """,
                safe_rows,
            )
            conn.commit()

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
                "SELECT * FROM tools WHERE tool_code LIKE ?",
                (f"%{query}%",),
            )
            return cursor.fetchall()

    def _sanitize_row(self, row: Sequence[str | None]) -> Tuple[str, str, str, str | None]:
        try:
            tool_code, tool_type, params, image_path = row
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("Row must have exactly four elements") from exc

        tool_code = str(tool_code).strip()
        tool_type = str(tool_type).strip().lower()
        params = str(params).strip()
        image_path = str(image_path) if image_path is not None else None

        if tool_type not in ALLOWED_TOOL_TYPES:
            raise ValueError(f"Unsupported tool type: {tool_type}")
        if not tool_code:
            raise ValueError("Tool code cannot be empty")

        return tool_code, tool_type, params, image_path


class OCRService:
    def __init__(self, db: ToolDatabase):
        self.db = db

    def read_drawing(self, image_path: str, tool_type: str = "drill") -> List[Tuple[str, str, str, None]]:
        if not OCR_AVAILABLE:
            raise RuntimeError("OCR stack is not installed. Install opencv-python and pytesseract.")
        if tool_type not in ALLOWED_TOOL_TYPES:
            raise ValueError(f"Unsupported tool type: {tool_type}")

        image_path_obj = Path(image_path).expanduser().resolve()
        if not image_path_obj.exists():
            raise FileNotFoundError(f"Image not found: {image_path_obj}")

        img = cv2.imread(str(image_path_obj))
        if img is None:
            raise ValueError(f"Cannot read image: {image_path_obj}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(
            gray, 180, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        custom_config = r"--oem 3 --psm 6"
        text = pytesseract.image_to_string(thresh, config=custom_config)

        rows: List[Tuple[str, str, str, None]] = []
        for line in text.splitlines():
            parts = line.split()
            if len(parts) > 1:
                code = parts[0]
                params = ";".join(
                    [f"p{i}={val}" for i, val in enumerate(parts[1:], start=1)]
                )
                rows.append((code, tool_type, params, None))
        return rows

    def import_from_image(self, image_path: str, tool_type: str = "drill") -> int:
        rows = self.read_drawing(image_path, tool_type)
        if rows:
            self.db.insert_tools(rows)
        return len(rows)


class ToolApp:
    """Tkinter GUI wrapper. Intended for desktop environments only."""

    def __init__(self, root: tk.Tk, db: ToolDatabase, ocr: OCRService | None):
        self.db = db
        self.ocr = ocr
        self.root = root
        self.root.title("Tool Card Generator")
        self.root.geometry("950x600")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        self.frame1 = ttk.Frame(self.notebook)
        self.notebook.add(self.frame1, text="📥 Импорт чертежа")

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
            self.frame2, columns=("id", "tool_code", "type", "params", "image"), show="headings"
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

    def load_image(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not path:
            return
        if not self.ocr:
            self.label_result.config(text="OCR не доступен в данной среде")
            return
        try:
            imported = self.ocr.import_from_image(path, "drill")
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

    import_parser = subparsers.add_parser(
        "import-drawing", help="Run OCR on an image and persist results"
    )
    import_parser.add_argument("image", type=str, help="Path to the drawing image")
    import_parser.add_argument(
        "--tool-type",
        default="drill",
        choices=sorted(ALLOWED_TOOL_TYPES),
        help="Type of tool represented in the drawing",
    )

    search_parser = subparsers.add_parser("search", help="Search tools by code fragment")
    search_parser.add_argument("query", type=str, help="Code fragment to look up")

    add_img_parser = subparsers.add_parser("add-image", help="Attach an image to a tool")
    add_img_parser.add_argument("tool_code", type=str, help="Tool code to update")
    add_img_parser.add_argument("image", type=str, help="Image file to attach")

    subparsers.add_parser("gui", help="Launch the Tkinter desktop application")

    return parser


def run_cli(args: argparse.Namespace) -> None:
    db = ToolDatabase(args.db_path)

    if args.command == "init-db":
        db.initialize(seed=args.seed)
        LOGGER.info("Database initialized at %s", db.db_path)
        return

    if args.command == "import-drawing":
        ocr = OCRService(db)
        imported = ocr.import_from_image(args.image, args.tool_type)
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
