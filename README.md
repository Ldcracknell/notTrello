# notTrello (Tkinter)

A simple Trello-like task board built with Python and Tkinter.

Features:
- Five columns: To-Do, Blocked, Priority, In Progress, Complete
- Add tasks to any column
- Drag tasks between columns
- Backlog side panel: add items and move them into To-Do

## Requirements
- Python 3.8+
- Tkinter (bundled with standard Python on Windows)

## Run
Open PowerShell in the project folder and run:

```powershell
python .\app.py
```

If `python` maps to Python 2 on your system, try:

```powershell
py -3 .\app.py
```

## Notes
- This is a single-file app (`app.py`) with no external dependencies.
- Drag-and-drop uses a floating ghost window; drop a card over any column to move it.
- Scroll columns with the mouse wheel when hovered.
