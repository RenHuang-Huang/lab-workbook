"""Local calendar picker without external packages."""
import calendar,datetime as dt,tkinter as tk
from tkinter import ttk
from .ui_theme import FONT

class DatePicker(ttk.Frame):
    def __init__(self,parent,variable):
        super().__init__(parent);self.variable=variable;self.popup=None
        self.entry=ttk.Entry(self,textvariable=variable,width=12,font=(FONT,16),state='readonly')
        self.entry.pack(side='left');self.entry.bind('<Button-1>',lambda e:self.open())
        self.entry.bind('<Return>',lambda e:self.open());self.entry.bind('<space>',lambda e:self.open())
        self.button=ttk.Button(self,text='選日期',command=self.open,style='Quiet.TButton');self.button.pack(side='left',padx=(6,0))
        self.disabled=False
    def set_enabled(self,enabled):
        self.disabled=not enabled;self.button.config(state='normal' if enabled else 'disabled')
        self.entry.config(state='readonly' if enabled else 'disabled')
        if not enabled and self.popup:
            if self.popup.winfo_exists():self.popup.destroy()
            self.popup=None
    def open(self):
        if self.disabled:return
        if self.popup and self.popup.winfo_exists():self.popup.lift();return
        try:current=dt.date.fromisoformat(self.variable.get())
        except ValueError:current=dt.date.today()
        win=tk.Toplevel(self);self.popup=win;win.title('選擇工作日期');win.transient(self.winfo_toplevel());win.resizable(False,False)
        win.geometry(f'+{self.winfo_rootx()}+{self.winfo_rooty()+self.winfo_height()+5}')
        frame=ttk.Frame(win,padding=12);frame.pack();year=tk.IntVar(value=current.year);month=tk.IntVar(value=current.month)
        header=ttk.Frame(frame);header.pack(fill='x');days=ttk.Frame(frame);days.pack(pady=10)
        def choose(day):self.variable.set(day.isoformat());win.destroy();self.popup=None
        def render(*_):
            try:y=int(year.get());m=int(month.get());assert 1900<=y<=9999 and 1<=m<=12
            except (ValueError,AssertionError,tk.TclError):return
            for child in days.winfo_children():child.destroy()
            for col,name in enumerate('一二三四五六日'):ttk.Label(days,text=name,anchor='center',width=4).grid(row=0,column=col)
            for row,week in enumerate(calendar.monthcalendar(y,m),1):
                for col,d in enumerate(week):
                    if d:
                        b=ttk.Button(days,text=str(d),width=3,command=lambda date=dt.date(y,m,d):choose(date))
                        b.grid(row=row,column=col,padx=1,pady=1)
                        if dt.date(y,m,d)==current:b.state(['pressed'])
        def move(offset):
            try:y=int(year.get());m=int(month.get())+offset
            except (ValueError,tk.TclError):return
            if m<1:y-=1;m=12
            if m>12:y+=1;m=1
            if 1900<=y<=9999:year.set(y);month.set(m);render()
        ttk.Button(header,text='‹',width=2,command=lambda:move(-1)).pack(side='left')
        ys=ttk.Spinbox(header,from_=1900,to=9999,textvariable=year,width=6,command=render);ys.pack(side='left',padx=3)
        ms=ttk.Combobox(header,values=list(range(1,13)),textvariable=month,width=3,state='readonly');ms.pack(side='left')
        ttk.Label(header,text='月').pack(side='left');ttk.Button(header,text='›',width=2,command=lambda:move(1)).pack(side='left',padx=3)
        ys.bind('<Return>',render);ys.bind('<FocusOut>',render);ms.bind('<<ComboboxSelected>>',render)
        ttk.Button(frame,text='今天',command=lambda:choose(dt.date.today())).pack(fill='x')
        win.bind('<Escape>',lambda e:win.destroy());render();win.grab_set()
