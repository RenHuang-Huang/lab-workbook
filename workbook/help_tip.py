"""Small contextual help, available by hover or keyboard focus."""
import tkinter as tk
from tkinter import ttk


def help_icon(parent,text):
    icon=ttk.Label(parent,text='?',width=2,anchor='center',cursor='question_arrow',takefocus=True,
                   foreground='#007F92',font=('Microsoft JhengHei UI',11,'bold'))
    popup=None;job=None
    def hide(event=None):
        nonlocal popup,job
        if job is not None:icon.after_cancel(job);job=None
        if popup is not None:popup.destroy();popup=None
    def show():
        nonlocal popup,job
        job=None
        value=text() if callable(text) else text
        if not value or not icon.winfo_ismapped():return
        popup=tk.Toplevel(icon);popup.wm_overrideredirect(True)
        ttk.Label(popup,text=value,wraplength=460,justify='left',padding=(12,9),relief='solid',borderwidth=1).pack()
        popup.update_idletasks()
        x=min(icon.winfo_rootx(),icon.winfo_screenwidth()-popup.winfo_reqwidth()-12)
        y=icon.winfo_rooty()+icon.winfo_height()+4
        if y+popup.winfo_reqheight()>icon.winfo_screenheight():y=icon.winfo_rooty()-popup.winfo_reqheight()-4
        popup.geometry(f'+{max(0,x)}+{max(0,y)}')
    def schedule(event=None):
        nonlocal job
        hide();job=icon.after(250,show)
    icon.bind('<Enter>',schedule);icon.bind('<Leave>',hide)
    icon.bind('<FocusIn>',schedule);icon.bind('<FocusOut>',hide)
    icon.bind('<Escape>',hide);icon.bind('<Button-1>',lambda e:(hide(),show()))
    icon.bind('<Destroy>',lambda e:hide() if e.widget is icon else None)
    return icon
