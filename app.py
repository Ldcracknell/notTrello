import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional
import json
import os
import ctypes

# Simple Tkinter board with drag-and-drop and a backlog tab

# Dark mode palette
APP_BG = "#202020"       # slate-900
FG = "#FFFFFF"           # gray-200
CARD_BG = "#3A3A3A"      # slate-800
CARD_BORDER = "#FFFFFF"   # gray-700
CARD_HOVER = "#2F2F42"    # slightly lighter hover

COLUMNS = [
    ("To-Do", "#1E293B"),      # slate-ish
    ("Blocked", "#331B1B"),    # maroon-ish
    ("Priority", "#332611"),   # brown-ish
    ("In Progress", "#21162B"),# dark green-ish
    ("Complete", "#162B1A"),   # slate
]

# Scrolling behavior
NATURAL_SCROLL = True  # If True, content moves in the same direction as wheel/gesture

class DragState:
    def __init__(self):
        self.card: Optional[tk.Frame] = None
        self.ghost: Optional[tk.Toplevel] = None
        self.offset_x = 0
        self.offset_y = 0

class ScrollableColumn(ttk.Frame):
    def __init__(self, master, title: str, color: str, allow_add: bool = False, allow_clear: bool = False):
        super().__init__(master, padding=(6, 6, 6, 6))
        self.title = title
        self.color = color
        self.allow_add = allow_add
        self.allow_clear = allow_clear

        # Header
        header = ttk.Frame(self)
        header.pack(fill=tk.X)
        ttk.Label(header, text=title, font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        # Pack right-side actions (Add, Clear) if enabled
        if self.allow_add:
            ttk.Button(header, text="+ Add", command=self._prompt_new_card).pack(side=tk.RIGHT)
        if self.allow_clear:
            ttk.Button(header, text="Clear", command=self._clear_all).pack(side=tk.RIGHT, padx=(0, 4))

        # Scrollable area
        outer = tk.Frame(self, bg=color, bd=0, highlightthickness=1, highlightbackground=CARD_BORDER)
        outer.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        self.canvas = tk.Canvas(outer, bg=color, highlightthickness=0)
        vbar = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.inner = tk.Frame(self.canvas, bg=color)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
    # Scrolling is handled globally at the App level; no per-column hover binding needed

    def _on_inner_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.inner_id, width=event.width)

    def _on_mousewheel(self, event):
        # Windows/macOS: delta in steps of 120 (Windows) or varying (macOS). Only scroll if pointer is over this column.
        if not self._pointer_inside():
            return
        delta = event.delta
        # Normalize and apply natural vs traditional direction
        base = int(delta / 120) if delta else 0
        if base == 0:
            base = 1 if delta > 0 else -1
        steps = base if NATURAL_SCROLL else -base
        self.canvas.yview_scroll(steps, "units")

    def _on_mousewheel_linux(self, event):
        # Linux typically uses Button-4 (up) and Button-5 (down)
        if not self._pointer_inside():
            return
        if event.num == 4:  # up
            self.canvas.yview_scroll(3 if NATURAL_SCROLL else -3, "units")
        elif event.num == 5:  # down
            self.canvas.yview_scroll(-3 if NATURAL_SCROLL else 3, "units")

    def _activate_mousewheel(self, _):
        # Bind globally while hovered so children also trigger scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _deactivate_mousewheel(self, _):
        # Remove global bindings when leaving this column
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _pointer_inside(self) -> bool:
        try:
            px, py = self.winfo_pointerx(), self.winfo_pointery()
            x1, y1 = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
            x2 = x1 + self.canvas.winfo_width()
            y2 = y1 + self.canvas.winfo_height()
            return x1 <= px <= x2 and y1 <= py <= y2
        except Exception:
            return False

    def _prompt_new_card(self):
        def on_ok():
            title = title_entry.get().strip()
            desc = desc_txt.get("1.0", "end").strip()
            win.destroy()
            if title:
                self.add_card(title, desc)
                # Persist after creating a new card
                try:
                    self._get_app().save_state()
                except Exception:
                    pass
        win = tk.Toplevel(self)
        win.title(f"Add to {self.title}")
        win.geometry("360x280")
        # Try to darken the native title bar on Windows
        try:
            self._get_app()._apply_dark_titlebar(win.winfo_id())
        except Exception:
            pass
        ttk.Label(win, text="Task title:").pack(anchor="w", padx=10, pady=(10, 4))
        title_entry = ttk.Entry(win)
        title_entry.pack(fill=tk.X, padx=10)
        title_entry.focus_set()
        # Description
        ttk.Label(win, text="Description (optional):").pack(anchor="w", padx=10, pady=(10, 4))
        desc_txt = tk.Text(win, height=6, bg=CARD_BG, fg=FG, insertbackground=FG, wrap="word")
        desc_txt.pack(fill=tk.BOTH, expand=True, padx=10)
        # Allow Enter to confirm Add (on title field)
        title_entry.bind("<Return>", lambda e: on_ok())
        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, pady=10)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="Add", command=on_ok).pack(side=tk.RIGHT)

    def add_card(self, text: str, desc: str = ""):
        card = TaskCard(self.inner, text=text, desc=desc)
        card.pack(fill=tk.X, padx=8, pady=6)
        card.update_idletasks()
        return card

    def _clear_all(self):
        # Confirm and clear all cards in this column
        if messagebox.askyesno("Clear", f"Delete all tasks in '{self.title}'?"):
            self.clear()
            try:
                self._get_app().save_state()
            except Exception:
                pass

    def get_cards_texts(self):
        texts = []
        for child in self.inner.winfo_children():
            if isinstance(child, TaskCard):
                texts.append(child.text.get())
        return texts

    def get_cards_data(self):
        items = []
        for child in self.inner.winfo_children():
            if isinstance(child, TaskCard):
                items.append({"title": child.text.get(), "desc": child.desc.get()})
        return items

    def clear(self):
        for child in list(self.inner.winfo_children()):
            if isinstance(child, TaskCard):
                child.destroy()

    def _get_app(self):
        w = self
        while getattr(w, "master", None) is not None:
            w = w.master
        return w  # type: ignore

class TaskCard(tk.Frame):
    def __init__(self, master, text: str, desc: str = ""):
        super().__init__(master, bg=CARD_BG, highlightthickness=1, highlightbackground=CARD_BORDER, bd=0)
        self.text = tk.StringVar(value=text)
        self.desc = tk.StringVar(value=desc)

        # Title label
        self.lbl = tk.Label(
            self,
            textvariable=self.text,
            bg=CARD_BG,
            fg=FG,
            wraplength=220,
            justify=tk.LEFT,
            anchor="w",
            padx=8,
            pady=6,
        )
        self.lbl.pack(fill=tk.X)

        # Button row; its gap should also be draggable
        self.btns = tk.Frame(self, bg=CARD_BG)
        self.btns.pack(fill=tk.X, padx=6, pady=(0, 6))
        self.edit_btn = ttk.Button(self.btns, text="View", width=6, command=self.view)
        self.del_btn = ttk.Button(self.btns, text="Delete", width=6, command=self.delete)
        self.edit_btn.pack(side=tk.LEFT)
        self.del_btn.pack(side=tk.RIGHT)

        self.bind_events()
        self.bind("<Configure>", self._on_resize)

    def bind_events(self):
        # Hover styling
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.lbl.bind("<Enter>", self._on_enter)
        self.lbl.bind("<Leave>", self._on_leave)
        self.btns.bind("<Enter>", self._on_enter)
        self.btns.bind("<Leave>", self._on_leave)
        # Drag interactions: make the label and the gap (btns frame) draggable
        self.lbl.bind("<ButtonPress-1>", self._on_press)
        self.lbl.bind("<B1-Motion>", self._on_drag)
        self.lbl.bind("<ButtonRelease-1>", self._on_release)
        self.btns.bind("<ButtonPress-1>", self._on_press)
        self.btns.bind("<B1-Motion>", self._on_drag)
        self.btns.bind("<ButtonRelease-1>", self._on_release)

    def _on_resize(self, event):
        # Adjust wraplength for the label to fit the card width
        try:
            pad = 20
            self.lbl.configure(wraplength=max(100, event.width - pad))
        except Exception:
            pass

    def _on_enter(self, _):
        self.configure(bg=CARD_HOVER)
        self.lbl.configure(bg=CARD_HOVER, fg=FG)
        self.btns.configure(bg=CARD_HOVER)

    def _on_leave(self, _):
        self.configure(bg=CARD_BG)
        self.lbl.configure(bg=CARD_BG, fg=FG)
        self.btns.configure(bg=CARD_BG)

    def view(self):
        def on_ok():
            new_text = title_entry.get().strip()
            new_desc = desc_txt.get("1.0", "end").strip()
            win.destroy()
            if new_text:
                self.text.set(new_text)
                self.desc.set(new_desc)
                try:
                    self._get_app().save_state()
                except Exception:
                    pass

        def move_to_backlog():
            new_text = title_entry.get().strip()
            new_desc = desc_txt.get("1.0", "end").strip()
            if not new_text:
                try:
                    messagebox.showwarning("Missing title", "Please enter a task title before moving to Backlog.")
                except Exception:
                    pass
                return
            app = self._get_app()
            # Add to backlog
            try:
                if hasattr(app, "backlog") and app.backlog:
                    app.backlog.add_item(new_text, new_desc)
            except Exception:
                pass
            # Remove this card from its column
            try:
                self.destroy()
            except Exception:
                pass
            # Close the view window and persist
            try:
                win.destroy()
            except Exception:
                pass
            try:
                app.save_state()
            except Exception:
                pass

        win = tk.Toplevel(self)
        win.title("View task")
        win.geometry("420x340")
        try:
            self._get_app()._apply_dark_titlebar(win.winfo_id())
        except Exception:
            pass
        ttk.Label(win, text="Task title:").pack(anchor="w", padx=10, pady=(10, 4))
        title_entry = ttk.Entry(win)
        title_entry.insert(0, self.text.get())
        title_entry.pack(fill=tk.X, padx=10)
        title_entry.focus_set()
        ttk.Label(win, text="Description:").pack(anchor="w", padx=10, pady=(10, 4))
        desc_txt = tk.Text(win, height=10, bg=CARD_BG, fg=FG, insertbackground=FG, wrap="word")
        desc_txt.pack(fill=tk.BOTH, expand=True, padx=10)
        desc_txt.insert("1.0", self.desc.get())
        title_entry.bind("<Return>", lambda e: on_ok())
        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, pady=10)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="Save", command=on_ok).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Move to Backlog", command=move_to_backlog).pack(side=tk.LEFT)

    def delete(self):
        if messagebox.askyesno("Delete", "Delete this task?"):
            self.destroy()
            try:
                self._get_app().save_state()
            except Exception:
                pass

    def _on_press(self, event):
        app = self._get_app()
        app.drag.card = self
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty()
        app.drag.offset_x = event.x
        app.drag.offset_y = event.y
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        ghost.attributes("-alpha", 0.85)
        ghost.configure(bg=CARD_BG)
        lbl = tk.Label(
            ghost,
            text=self.text.get(),
            bg=CARD_BG,
            fg=FG,
            padx=10,
            pady=6,
            justify=tk.LEFT,
            wraplength=240,
        )
        lbl.pack()
        ghost.geometry(f"+{x}+{y}")
        app.drag.ghost = ghost

    def _on_drag(self, event):
        app = self._get_app()
        if app.drag.ghost is None:
            return
        gx = self.winfo_pointerx() - app.drag.offset_x
        gy = self.winfo_pointery() - app.drag.offset_y
        app.drag.ghost.geometry(f"+{gx}+{gy}")

    def _on_release(self, _):
        app = self._get_app()
        ghost = app.drag.ghost
        if ghost is None:
            return
        px, py = self.winfo_pointerx(), self.winfo_pointery()
        target_col = app.column_under_pointer(px, py)
        ghost.destroy()
        app.drag.ghost = None
        app.drag.card = None
        if target_col is not None:
            text = self.text.get()
            desc = self.desc.get()
            self.destroy()
            app.add_card_to_column(target_col, text, desc)
            try:
                app.save_state()
            except Exception:
                pass

    def _get_app(self):
        w = self
        while getattr(w, "master", None) is not None:
            w = w.master
        return w  # type: ignore

class BacklogPanel(ttk.Frame):
    def __init__(self, master, on_move_to_todo):
        super().__init__(master, padding=(6, 6, 6, 6))
        self.on_move_to_todo = on_move_to_todo
        # Parallel list to store descriptions for listbox items
        self._backlog_desc = []

        ttk.Label(self, text="Backlog", font=("Segoe UI", 11, "bold"), foreground=FG).pack(anchor="w")

        add_row = ttk.Frame(self)
        add_row.pack(fill=tk.X, pady=(6, 6))
        self.entry = ttk.Entry(add_row)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Allow Enter to trigger Add
        self.entry.bind("<Return>", lambda e: self._add())
        ttk.Button(add_row, text="Add", command=self._add).pack(side=tk.LEFT, padx=(6, 0))

        # Optional description field
        desc_row = ttk.Frame(self)
        desc_row.pack(fill=tk.BOTH, expand=False, pady=(0, 6))
        ttk.Label(desc_row, text="Description (optional):").pack(anchor="w")
        self.desc_txt = tk.Text(desc_row, height=4, bg=CARD_BG, fg=FG, insertbackground=FG, wrap="word")
        self.desc_txt.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(
            list_frame,
            height=20,
            bg=CARD_BG,
            fg=FG,
            selectbackground="#334155",
            selectforeground=FG,
            highlightthickness=1,
            highlightbackground=CARD_BORDER,
            relief="flat",
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=sb.set)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btns, text="To To-Do", command=self._move_selected_to_todo).pack(side=tk.LEFT)
        ttk.Button(btns, text="Delete", command=self._delete_selected).pack(side=tk.RIGHT)

    def add_item(self, title: str, desc: str = ""):
        title = (title or "").strip()
        if not title:
            return
        self.listbox.insert(tk.END, title)
        self._backlog_desc.append(desc or "")
        # Persist after programmatic add
        try:
            self._get_app().save_state()
        except Exception:
            pass

    def _add(self):
        text = self.entry.get().strip()
        desc = self.desc_txt.get("1.0", "end").strip()
        if text:
            self.listbox.insert(tk.END, text)
            self._backlog_desc.append(desc)
            self.entry.delete(0, tk.END)
            self.desc_txt.delete("1.0", "end")
            # Persist after adding backlog item
            try:
                self._get_app().save_state()
            except Exception:
                pass

    def _move_selected_to_todo(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        text = self.listbox.get(idx)
        desc = self._backlog_desc.pop(idx) if 0 <= idx < len(self._backlog_desc) else ""
        self.listbox.delete(idx)
        self.on_move_to_todo(text, desc)
        # Persist after moving backlog -> To-Do
        try:
            self._get_app().save_state()
        except Exception:
            pass

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.listbox.delete(idx)
        if 0 <= idx < len(self._backlog_desc):
            self._backlog_desc.pop(idx)
        # Persist after delete
        try:
            self._get_app().save_state()
        except Exception:
            pass

    def get_items(self):
        items = []
        for i, title in enumerate(self.listbox.get(0, tk.END)):
            desc = self._backlog_desc[i] if i < len(self._backlog_desc) else ""
            items.append({"title": title, "desc": desc})
        return items

    def set_items(self, items):
        self.listbox.delete(0, tk.END)
        self._backlog_desc = []
        for it in items:
            if isinstance(it, dict):
                title = str(it.get("title", ""))
                desc = str(it.get("desc", ""))
                if title:
                    self.listbox.insert(tk.END, title)
                    self._backlog_desc.append(desc)
            else:
                txt = str(it)
                if txt:
                    self.listbox.insert(tk.END, txt)
                    self._backlog_desc.append("")

    def _get_app(self):
        w = self
        while getattr(w, "master", None) is not None:
            w = w.master
        return w  # type: ignore

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("notTrello")
        self.geometry("1200x700")
        self.minsize(860, 560)

        self.drag = DragState()

        # Where to store state
        self.state_path = os.path.join(os.path.dirname(__file__), "board_state.json")

        # Dark ttk styling and window background
        self.configure(bg=APP_BG)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=APP_BG)
        style.configure("TLabel", background=APP_BG, foreground=FG)
        style.configure("TNotebook", background=APP_BG)
        style.configure("TNotebook.Tab", background=CARD_BG, foreground=FG)
        style.map("TNotebook.Tab", background=[("selected", "#0B1220")])
        style.configure("TButton", background=CARD_BG, foreground=FG)
        style.configure("TEntry", fieldbackground=CARD_BG, foreground=FG, insertcolor=FG)

        # Tabs across the top: Board and Backlog
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        board_tab = ttk.Frame(notebook)
        backlog_tab = ttk.Frame(notebook)
        notebook.add(board_tab, text="Board")
        notebook.add(backlog_tab, text="Backlog")

        # Board tab: columns area
        self.columns_frame = ttk.Frame(board_tab)
        self.columns_frame.pack(fill=tk.BOTH, expand=True)

        self.columns: Dict[str, ScrollableColumn] = {}
        cols_holder = ttk.Frame(self.columns_frame)
        cols_holder.pack(fill=tk.BOTH, expand=True)
        cols_holder.grid_rowconfigure(0, weight=1)
        for idx, (title, color) in enumerate(COLUMNS):
            cols_holder.grid_columnconfigure(idx, weight=1, uniform="cols")
            col = ScrollableColumn(
                cols_holder,
                title,
                color,
                allow_add=(title == "To-Do"),
                allow_clear=(title == "Complete"),
            )
            col.grid(row=0, column=idx, sticky="nsew", padx=6, pady=6)
            self.columns[title] = col

        # Backlog tab
        self.backlog = BacklogPanel(backlog_tab, on_move_to_todo=lambda t, d="": self.add_card_to_column("To-Do", t, d))
        self.backlog.pack(fill=tk.BOTH, expand=True)

        # Enable natural/global mouse wheel scrolling over the column under the pointer
        self.bind_all("<MouseWheel>", self._on_global_mousewheel)
        self.bind_all("<Button-4>", self._on_global_mousewheel_linux)
        self.bind_all("<Button-5>", self._on_global_mousewheel_linux)

        # Load saved data or seed with sample data
        loaded = self.load_state()
        if not loaded:
            self.add_card_to_column("To-Do", "Try adding and dragging tasks")
            self.add_card_to_column("Priority", "High-priority item")
            self.add_card_to_column("In Progress", "Working on the UI")

        # Save on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # Darken the main window's native title bar on Windows
        try:
            self._apply_dark_titlebar(self.winfo_id())
            # Re-apply shortly after the window is realized to ensure it sticks
            self.after(200, lambda: self._apply_dark_titlebar(self.winfo_id()))
        except Exception:
            pass

    def _on_global_mousewheel(self, event):
        # Route scroll to the column under the pointer
        px, py = self.winfo_pointerx(), self.winfo_pointery()
        title = self.column_under_pointer(px, py)
        if not title:
            return
        col = self.columns.get(title)
        if not col:
            return
        delta = event.delta
        base = int(delta / 120) if delta else 0
        if base == 0:
            base = 1 if delta > 0 else -1
        steps = base if NATURAL_SCROLL else -base
        col.canvas.yview_scroll(steps, "units")
        return "break"

    def _on_global_mousewheel_linux(self, event):
        # Route Linux scroll buttons to the column under the pointer
        px, py = self.winfo_pointerx(), self.winfo_pointery()
        title = self.column_under_pointer(px, py)
        if not title:
            return
        col = self.columns.get(title)
        if not col:
            return
        if event.num == 4:  # up
            col.canvas.yview_scroll(3 if NATURAL_SCROLL else -3, "units")
        elif event.num == 5:  # down
            col.canvas.yview_scroll(-3 if NATURAL_SCROLL else 3, "units")
        return "break"

    def add_card_to_column(self, column_title: str, text: str, desc: str = ""):
        col = self.columns.get(column_title)
        if not col:
            return
        col.add_card(text, desc)

    def column_under_pointer(self, px: int, py: int) -> Optional[str]:
        for title, col in self.columns.items():
            x1 = col.winfo_rootx()
            y1 = col.winfo_rooty()
            x2 = x1 + col.winfo_width()
            y2 = y1 + col.winfo_height()
            if x1 <= px <= x2 and y1 <= py <= y2:
                return title
        return None

    # Persistence
    def save_state(self):
        data = {
            # Store title+desc per card
            "columns": {title: (col.get_cards_data() if hasattr(col, "get_cards_data") else [
                {"title": t, "desc": ""} for t in col.get_cards_texts()
            ]) for title, col in self.columns.items()},
            "backlog": self.backlog.get_items() if hasattr(self, "backlog") else [],
        }
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # Non-blocking; show a gentle message
            try:
                messagebox.showwarning("Save failed", f"Could not save board: {e}")
            except Exception:
                pass

    def load_state(self) -> bool:
        if not os.path.exists(self.state_path):
            return False
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return False

        # Restore columns
        cols_data = data.get("columns", {})
        restored_any = False
        for title, col in self.columns.items():
            items = cols_data.get(title)
            if isinstance(items, list):
                col.clear()
                for it in items:
                    if isinstance(it, dict):
                        title_txt = str(it.get("title", "")).strip()
                        desc_txt = str(it.get("desc", ""))
                        if title_txt:
                            col.add_card(title_txt, desc_txt)
                            restored_any = True
                    elif isinstance(it, str):
                        txt = it.strip()
                        if txt:
                            col.add_card(txt)
                            restored_any = True

        # Restore backlog
        backlog_items = data.get("backlog", [])
        if isinstance(backlog_items, list):
            # Accept both legacy string list and new dict list
            items_norm = []
            for it in backlog_items:
                if isinstance(it, dict):
                    items_norm.append({"title": str(it.get("title", "")), "desc": str(it.get("desc", ""))})
                else:
                    items_norm.append(str(it))
            self.backlog.set_items(items_norm)
            if backlog_items:
                restored_any = True

        return restored_any

    def on_close(self):
        try:
            self.save_state()
        finally:
            self.destroy()

if __name__ == "__main__":
    App().mainloop()
