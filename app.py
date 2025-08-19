import sys, os, subprocess, datetime, sqlite3
from pathlib import Path
from PyQt6 import QtWidgets, QtGui, QtCore

APP_TITLE = "B4RT Mod Launcher"
APP_DIR = Path(__file__).resolve().parent
DB_FILE = APP_DIR / "mods.db"

# ------------------ Inline QSS ------------------
INLINE_QSS = """
QMainWindow { background-color: #171a1f; }
QToolBar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #20242b, stop:1 #181b21); padding:6px; border:none; }
QToolBar QToolButton, QToolBar QPushButton { color:#d7d7d7; padding:6px 10px; border-radius:4px; }
QToolBar QToolButton:hover, QToolBar QPushButton:hover { background-color:#2b313b; }
QLabel { color:#aab0bb; }
QLineEdit { background:#242a33; color:#e6e9ee; border:1px solid #2e3440; border-radius:4px; padding:6px 8px; }
QLineEdit:focus { border:1px solid #3f8edc; }
QComboBox { background:#242a33; color:#e6e9ee; border:1px solid #2e3440; border-radius:4px; padding:4px 6px; }
QComboBox QAbstractItemView { background:#242a33; color:#e6e9ee; selection-background-color:#0b6fb8; }
QTableWidget { background:#1f232b; color:#e6e9ee; gridline-color:#2f3541; alternate-background-color:#1b1f26; selection-background-color:#0b6fb8; selection-color:white; font-size:14px; }
QHeaderView::section { background:#262b33; color:#b6beca; padding:6px 8px; border:none; border-right:1px solid #2e3440; }
QTableCornerButton::section { background:#262b33; border:none; }
QPushButton { background:#2a313c; color:#e6e9ee; border:1px solid #343b48; border-radius:4px; padding:6px 12px; }
QPushButton:hover { background:#323a46; }
"""

def toolbar_spacer(width: int = 8) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    w.setFixedWidth(width)
    w.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
    return w

# ====================== DB LAYER ======================
def db_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def _column_exists(con, table, col):
    cur = con.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())

def db_init():
    with db_connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS mods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cover_path TEXT NOT NULL DEFAULT '',
                bat_path TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Ready',
                last_run INTEGER NOT NULL DEFAULT 0
            )
        """)
        # migrations
        if not _column_exists(con, "mods", "version"):
            con.execute("ALTER TABLE mods ADD COLUMN version TEXT NOT NULL DEFAULT ''")
        if not _column_exists(con, "mods", "category"):
            con.execute("ALTER TABLE mods ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        if not _column_exists(con, "mods", "blend_path"):
            con.execute("ALTER TABLE mods ADD COLUMN blend_path TEXT NOT NULL DEFAULT ''")
        if not _column_exists(con, "mods", "work_path"):
            con.execute("ALTER TABLE mods ADD COLUMN work_path TEXT NOT NULL DEFAULT ''")
        con.commit()

def db_fetch_all(name_filter: str | None = None, category_filter: str | None = None):
    with db_connect() as con:
        q = "SELECT * FROM mods WHERE 1=1"
        args = []
        if name_filter:
            q += " AND LOWER(name) LIKE ?"
            args.append(f"%{name_filter.lower()}%")
        if category_filter and category_filter.lower() != "__all__":
            q += " AND category = ?"
            args.append(category_filter)
        q += " ORDER BY name ASC"
        return list(con.execute(q, args))

def db_distinct_categories():
    with db_connect() as con:
        rows = con.execute(
            "SELECT DISTINCT category FROM mods WHERE TRIM(category) <> '' ORDER BY category COLLATE NOCASE"
        ).fetchall()
        return [r[0] for r in rows if r[0]]

def db_insert(mod: dict) -> int:
    with db_connect() as con:
        cur = con.execute("""
            INSERT INTO mods (name, cover_path, bat_path, status, last_run, version, category, blend_path, work_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mod.get("name",""),
            mod.get("cover_path",""),
            mod.get("bat_path",""),
            mod.get("status","Ready"),
            int(mod.get("last_run", 0)),
            mod.get("version","").strip(),
            mod.get("category","").strip(),
            mod.get("blend_path","").strip(),
            mod.get("work_path","").strip(),
        ))
        con.commit()
        return cur.lastrowid

def db_update(mod_id: int, mod: dict):
    with db_connect() as con:
        con.execute("""
            UPDATE mods
               SET name = ?, cover_path = ?, bat_path = ?, status = ?, last_run = ?, version = ?, category = ?, blend_path = ?, work_path = ?
             WHERE id = ?
        """, (
            mod.get("name",""),
            mod.get("cover_path",""),
            mod.get("bat_path",""),
            mod.get("status","Ready"),
            int(mod.get("last_run", 0)),
            mod.get("version","").strip(),
            mod.get("category","").strip(),
            mod.get("blend_path","").strip(),
            mod.get("work_path","").strip(),
            mod_id
        ))
        con.commit()

def db_delete(mod_id: int):
    with db_connect() as con:
        con.execute("DELETE FROM mods WHERE id = ?", (mod_id,))
        con.commit()

def db_update_run(mod_id: int, status: str, last_run_ts: int):
    with db_connect() as con:
        con.execute("UPDATE mods SET status = ?, last_run = ? WHERE id = ?",
                    (status, int(last_run_ts), mod_id))
        con.commit()

# ====================== UTIL ======================
def human_time(ts: int | float):
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

def load_styles(app: QtWidgets.QApplication):
    QtWidgets.QApplication.setStyle("Fusion")
    app.setStyleSheet(INLINE_QSS)
    print("[QSS] Using inline stylesheet.")

# ---------- Cover cell widget (image only) ----------
class CoverCell(QtWidgets.QLabel):
    def __init__(self, cover_path: str, w: int, h: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(w, h)
        self.setScaledContents(True)
        if cover_path and Path(cover_path).exists():
            pix = QtGui.QPixmap(cover_path)
            if not pix.isNull():
                scaled = pix.scaled(w, h,
                                    QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                    QtCore.Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(scaled)

# ====================== DIALOG ======================
class ModEditorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, mod=None, existing_categories=None):
        super().__init__(parent)
        self.setWindowTitle("Mod Settings")
        self.setModal(True)
        self.setMinimumWidth(720)

        existing_categories = existing_categories or []
        self.mod = mod or {
            "name":"", "version":"", "category":"", "cover_path":"", "bat_path":"",
            "blend_path":"", "work_path":"", "status":"Ready", "last_run":0
        }

        form = QtWidgets.QFormLayout()
        self.name_edit = QtWidgets.QLineEdit(self.mod.get("name",""))
        self.version_edit = QtWidgets.QLineEdit(self.mod.get("version",""))

        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(existing_categories)
        cur_cat = self.mod.get("category","").strip()
        if cur_cat and cur_cat not in existing_categories:
            self.category_combo.insertItem(0, cur_cat)
        if cur_cat:
            self.category_combo.setCurrentText(cur_cat)

        self.cover_edit = QtWidgets.QLineEdit(self.mod.get("cover_path",""))
        self.bat_edit   = QtWidgets.QLineEdit(self.mod.get("bat_path",""))
        self.blend_edit = QtWidgets.QLineEdit(self.mod.get("blend_path",""))
        self.work_edit  = QtWidgets.QLineEdit(self.mod.get("work_path",""))

        pick_cover = QtWidgets.QPushButton("Browse…"); pick_cover.clicked.connect(self.pick_cover)
        pick_bat   = QtWidgets.QPushButton("Browse…"); pick_bat.clicked.connect(self.pick_bat)
        pick_blend = QtWidgets.QPushButton("Browse…"); pick_blend.clicked.connect(self.pick_blend)
        pick_work  = QtWidgets.QPushButton("Browse…"); pick_work.clicked.connect(self.pick_work)

        cover_row = QtWidgets.QHBoxLayout(); cover_row.addWidget(self.cover_edit); cover_row.addWidget(pick_cover)
        bat_row   = QtWidgets.QHBoxLayout();   bat_row.addWidget(self.bat_edit);   bat_row.addWidget(pick_bat)
        blend_row = QtWidgets.QHBoxLayout(); blend_row.addWidget(self.blend_edit); blend_row.addWidget(pick_blend)
        work_row  = QtWidgets.QHBoxLayout();  work_row.addWidget(self.work_edit);  work_row.addWidget(pick_work)

        form.addRow("Mod Name:", self.name_edit)
        form.addRow("Version:", self.version_edit)
        form.addRow("Category:", self.category_combo)
        form.addRow("Cover Image:", cover_row)
        form.addRow("BAT/CMD File:", bat_row)
        form.addRow("Blend File (.blend):", blend_row)
        form.addRow("Project Folder (optional):", work_row)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form); layout.addWidget(btns)

    def pick_cover(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Cover", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if path: self.cover_edit.setText(path)

    def pick_bat(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select BAT/CMD", "", "Batch/CMD (*.bat *.cmd);;All files (*)"
        )
        if path: self.bat_edit.setText(path)

    def pick_blend(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Blend File", "", "Blender (*.blend);;All files (*)"
        )
        if path: self.blend_edit.setText(path)

    def pick_work(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Project Folder", "", QtWidgets.QFileDialog.Option.ShowDirsOnly
        )
        if path: self.work_edit.setText(path)

    def get_value(self):
        return {
            "name": self.name_edit.text().strip(),
            "version": self.version_edit.text().strip(),
            "category": self.category_combo.currentText().strip(),
            "cover_path": self.cover_edit.text().strip(),
            "bat_path": self.bat_edit.text().strip(),
            "blend_path": self.blend_edit.text().strip(),
            "work_path": self.work_edit.text().strip(),
            "status": self.mod.get("status","Ready"),
            "last_run": self.mod.get("last_run", 0)
        }

# ====================== MAIN WINDOW ======================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1600, 880)

        # Toolbar
        tb = QtWidgets.QToolBar(); tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(tb)

        add_act = QtGui.QAction("Add", self);   add_act.triggered.connect(self.add_mod)
        edit_act = QtGui.QAction("Edit", self); edit_act.triggered.connect(self.edit_selected)
        del_act = QtGui.QAction("Delete", self); del_act.triggered.connect(self.delete_selected)
        run_act = QtGui.QAction("Run ▶", self); run_act.triggered.connect(self.run_selected)
        blend_act = QtGui.QAction("Open Blend ⧉", self); blend_act.triggered.connect(self.open_blend_selected)

        # ---- Base Folder button (left-click open, right-click set) ----
        self.base_folder_action = QtGui.QAction("Base Folder", self)
        self.base_folder_action.triggered.connect(self.open_base_folder)

        self.base_folder_button = QtWidgets.QToolButton()
        self.base_folder_button.setDefaultAction(self.base_folder_action)
        self.base_folder_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.base_folder_button.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.base_folder_button.customContextMenuRequested.connect(self._show_base_folder_menu)

        # Build toolbar
        tb.addAction(add_act); tb.addAction(edit_act); tb.addAction(del_act)
        tb.addSeparator(); tb.addAction(run_act); tb.addAction(blend_act)
        tb.addSeparator(); tb.addWidget(self.base_folder_button); tb.addSeparator()

        # Category filter
        tb.addWidget(QtWidgets.QLabel("  Category: "))
        self.category_filter = QtWidgets.QComboBox()
        self.category_filter.setMinimumWidth(180)
        self.category_filter.currentIndexChanged.connect(self.refresh)
        tb.addWidget(self.category_filter)
        tb.addWidget(toolbar_spacer(8))

        # Name filter
        tb.addWidget(QtWidgets.QLabel("  Search: "))
        self.search_edit = QtWidgets.QLineEdit(placeholderText="Filter by name…")
        self.search_edit.textChanged.connect(self.refresh)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(360)
        tb.addWidget(self.search_edit)

        # Table and sizes
        self.BANNER_W, self.BANNER_H = 321, 150  # cover size
        self.table = QtWidgets.QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels(["ID", "Cover", "MOD NAME", "Version", "Category", "Last Run", "Path", "Blend Path"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(self.BANNER_H + 18)
        self.setCentralWidget(self.table)

        # Fonts: name bigger; others default via QSS
        self.name_font = QtGui.QFont(self.font())
        self.name_font.setPointSize(self.font().pointSize() + 4)

        # Column sizing
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)  # ID small
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Fixed)             # Cover fixed
        hdr.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)           # Name stretches
        hdr.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Interactive)       # Version
        hdr.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Interactive)       # Category
        hdr.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Interactive)       # Last Run
        hdr.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeMode.Interactive)       # Path
        hdr.setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeMode.Interactive)       # Blend Path
        self.table.setColumnWidth(1, self.BANNER_W + 4)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 160)
        self.table.setColumnWidth(5, 200)
        self.table.setColumnWidth(6, 420)
        self.table.setColumnWidth(7, 420)

        # Context menu
        self.table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)

        # Double click runs
        self.table.doubleClicked.connect(self.run_selected)

        # Rows cache
        self.rows = []

        # Initialize category, data, and base folder tooltip
        self.refresh_categories()
        self.refresh()
        self._set_base_folder(str(self._get_base_folder()))

    # ----- Base folder: settings + actions -----
    def _settings(self) -> QtCore.QSettings:
        return QtCore.QSettings("B4RT", "ModLauncher")

    def _get_base_folder(self) -> Path:
        val = self._settings().value("base_folder", str(APP_DIR))
        return Path(val)

    def _set_base_folder(self, path: str):
        self._settings().setValue("base_folder", path or "")
        self.base_folder_action.setToolTip(f"Open Base Folder\n{path or '(not set)'}")

    def open_base_folder(self):
        p = self._get_base_folder()
        if not p.exists():
            QtWidgets.QMessageBox.information(
                self, "Base Folder",
                "Base folder is not set or does not exist.\nRight‑click this button to set it."
            )
            return
        try:
            self._open_path_with_os(p)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open base folder:\n{e}")

    def choose_base_folder(self):
        start = str(self._get_base_folder())
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select B4RT BASE FOLDER", start, QtWidgets.QFileDialog.Option.ShowDirsOnly
        )
        if path:
            self._set_base_folder(path)

    def _show_base_folder_menu(self, pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Set Base Folder…", self.choose_base_folder)
        btn = self.base_folder_button
        menu.exec(btn.mapToGlobal(pos))

    # ----- helpers -----
    def refresh_categories(self):
        cats = db_distinct_categories()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All", userData="__all__")
        for c in cats:
            self.category_filter.addItem(c, userData=c)
        self.category_filter.blockSignals(False)

    def current_category_filter(self):
        data = self.category_filter.currentData()
        return data if data is not None else "__all__"

    def context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Run ▶", self.run_selected)
        menu.addAction("Open Blend ⧉", self.open_blend_selected)
        menu.addAction("Open Project Folder", self.open_project_folder_selected)
        menu.addSeparator()
        menu.addAction("Edit", self.edit_selected)
        menu.addAction("Delete", self.delete_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def current_row_index(self) -> int:
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows: return -1
        return next(iter(rows))

    def selected_id(self) -> int | None:
        idx = self.current_row_index()
        if idx < 0: return None
        return int(self.rows[idx]["id"])

    # ----- CRUD -----
    def add_mod(self):
        dlg = ModEditorDialog(self, existing_categories=db_distinct_categories())
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            v = dlg.get_value()
            if v["name"]:
                db_insert(v)
                self.refresh_categories()
                self.refresh(select_name=v["name"])

    def edit_selected(self):
        idx = self.current_row_index()
        if idx < 0: return
        row = self.rows[idx]
        current = {
            "name": row["name"],
            "version": row["version"],
            "category": row["category"],
            "cover_path": row["cover_path"],
            "bat_path": row["bat_path"],
            "blend_path": row["blend_path"] if "blend_path" in row.keys() else "",
            "work_path": row["work_path"] if "work_path" in row.keys() else "",
            "status": row["status"],
            "last_run": row["last_run"]
        }
        dlg = ModEditorDialog(self, mod=current, existing_categories=db_distinct_categories())
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            updated = dlg.get_value()
            db_update(row["id"], updated)
            self.refresh_categories()
            self.refresh(select_name=updated["name"])

    def delete_selected(self):
        sel_id = self.selected_id()
        if sel_id is None: return
        reply = QtWidgets.QMessageBox.question(self, "Delete", "Remove selected mod?")
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            db_delete(sel_id)
            self.refresh_categories()
            self.refresh()

    def run_selected(self):
        idx = self.current_row_index()
        if idx < 0: return
        row = self.rows[idx]
        bat = row["bat_path"]
        if not bat or not Path(bat).exists():
            QtWidgets.QMessageBox.warning(self, "Not found", "BAT/CMD path is empty or missing.")
            return
        try:
            subprocess.Popen(['cmd', '/c', bat], shell=False)
            now_ts = int(datetime.datetime.now().timestamp())
            db_update_run(row["id"], "Running", now_ts)
            self.refresh(select_name=row["name"])
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to run:\n{e}")

    # ----- open helpers -----
    def _open_path_with_os(self, p: Path):
        if sys.platform.startswith("win"):
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def open_blend_selected(self):
        idx = self.current_row_index()
        if idx < 0: return
        row = self.rows[idx]
        blend_path = (row["blend_path"] if "blend_path" in row.keys() else "").strip()
        if not blend_path:
            QtWidgets.QMessageBox.information(self, "No Blend File", "No .blend file set for this mod. Use Edit to set one.")
            return
        p = Path(blend_path)
        if not p.exists():
            QtWidgets.QMessageBox.warning(self, "Not found", f"Blend file not found:\n{blend_path}")
            return
        try:
            self._open_path_with_os(p)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open blend file:\n{e}")

    def open_project_folder_selected(self):
        idx = self.current_row_index()
        if idx < 0: return
        row = self.rows[idx]
        work_path = (row["work_path"] if "work_path" in row.keys() else "").strip()
        if not work_path:
            QtWidgets.QMessageBox.information(self, "No Project Folder", "No project/work folder set. Use Edit to set one.")
            return
        p = Path(work_path)
        if not p.exists():
            QtWidgets.QMessageBox.warning(self, "Not found", f"Project folder not found:\n{work_path}")
            return
        try:
            self._open_path_with_os(p)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to open project folder:\n{e}")

    # ----- table population -----
    def refresh(self, *_args, select_name=None):
        name_q = self.search_edit.text().strip()
        cat_q = self.current_category_filter()
        self.rows = db_fetch_all(name_q if name_q else None, cat_q)

        self.table.setRowCount(0)
        for r in self.rows:
            i = self.table.rowCount()
            self.table.insertRow(i)

            # ID
            id_item = QtWidgets.QTableWidgetItem(str(r["id"]))
            self.table.setItem(i, 0, id_item)

            # Cover widget
            cover_widget = CoverCell(r["cover_path"], self.BANNER_W, self.BANNER_H, self.table)
            self.table.setCellWidget(i, 1, cover_widget)

            # Name (bigger font)
            name_item = QtWidgets.QTableWidgetItem(r["name"])
            name_item.setFont(self.name_font)
            self.table.setItem(i, 2, name_item)

            # Version
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(r["version"] or ""))

            # Category
            self.table.setItem(i, 4, QtWidgets.QTableWidgetItem(r["category"] or ""))

            # Last Run
            last = r["last_run"] or 0
            self.table.setItem(i, 5, QtWidgets.QTableWidgetItem(human_time(last) if last else ""))

            # Path (BAT/CMD)
            self.table.setItem(i, 6, QtWidgets.QTableWidgetItem(r["bat_path"] or ""))

            # Blend Path (visible like before; hide if you prefer)
            blend_val = r["blend_path"] if "blend_path" in r.keys() else ""
            self.table.setItem(i, 7, QtWidgets.QTableWidgetItem(blend_val))

        # Reselect if needed
        if select_name:
            for r in range(self.table.rowCount()):
                if self.table.item(r, 2) and self.table.item(r, 2).text() == select_name:
                    self.table.selectRow(r)
                    break

# ====================== ENTRY ======================
def main():
    print(f"[DB] Using: {DB_FILE}")
    db_init()

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    load_styles(app)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
