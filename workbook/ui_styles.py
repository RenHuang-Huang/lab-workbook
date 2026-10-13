"""Readable, compact dictionary tables with DPI-aware row heights."""
from tkinter import ttk,font
from .ui_theme import FONT,INK,MUTED,LINE,LIGHT,PRIMARY

def readable_table(parent,pending=False):
    face=font.Font(root=parent,family=FONT,size=12)
    style=ttk.Style(parent)
    style.configure('Readable.Treeview',font=(FONT,12),rowheight=face.metrics('linespace')+14,
                    background='white',fieldbackground='white',foreground=INK,borderwidth=0)
    style.map('Readable.Treeview',background=[('selected',LIGHT)],foreground=[('selected','#006B7D')])
    if pending:
        # Selection uses row tags so unsaved yellow rows remain yellow when selected.
        style.map('Pending.Readable.Treeview',background=[],foreground=[])
    style.configure('Readable.Treeview.Heading',font=(FONT,10,'bold'),background='#EEF3F7',foreground=MUTED,padding=(8,9),relief='flat',bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.map('Readable.Treeview.Heading',background=[('active','#E4EEF1')])
    return 'Pending.Readable.Treeview' if pending else 'Readable.Treeview'
