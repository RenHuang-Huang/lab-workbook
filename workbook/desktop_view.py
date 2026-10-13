"""Three-page desktop presentation, independent of export/configuration rules."""
import tkinter as tk
import datetime as dt
import math
import time
from tkinter import ttk,font as tkfont
from .date_picker import DatePicker
from .version import APP_VERSION

from .ui_theme import BG,SURFACE,INK,MUTED,LINE,CONTROL,PRIMARY,LIGHT,FONT,theme,icon


class Navigation(ttk.Notebook):
    """Collapsible sidebar; notebook keeps page routing and Ctrl+Tab semantics."""
    def __init__(self,parent):
        self.shell=ttk.Frame(parent);self.shell.pack(fill='both',expand=True)
        self.rail_space=ttk.Frame(self.shell,width=44)
        self.rail_space.pack(side='left',fill='y',padx=(0,16));self.rail_space.pack_propagate(False)
        self.bar=ttk.Frame(self.shell,width=44)
        self.bar.place(x=0,y=0,width=44,relheight=1);self.bar.pack_propagate(False)
        super().__init__(self.shell,style='Main.TNotebook',takefocus=False)
        self.value=tk.StringVar();self.buttons=[];self.titles=[];self.slots=[]
        self.expanded=False;self.sections=None;self.sections_page=None;self.sections_open=True
        self.tooltip=None;self.leave_job=None;self.animation_job=None;self.closing=False
        self.bind('<<NotebookTabChanged>>',self.sync)
        self.winfo_toplevel().bind('<Leave>',self.pointer_left,add='+')
        self.winfo_toplevel().bind('<Enter>',self.pointer_entered,add='+')
        self.bind('<Destroy>',self.cancel_motion)
    def control_slot(self,bottom=False):
        slot=ttk.Frame(self.bar,height=44)
        # Reserve the settings footer before the accordion consumes remaining space.
        slot.pack(side='bottom' if bottom else 'top',fill='x',pady=(8,0) if bottom else (0,4))
        slot.pack_propagate(False)
        self.slots.append(slot);return slot
    def add(self,child,**options):
        super().add(child,**options)
        title=options.get('text','');index=len(self.buttons);self.titles.append(title)
        button=ttk.Radiobutton(self.control_slot(bottom=index==1),text=title,value=str(child),variable=self.value,
            image=nav_image(self.winfo_toplevel(),('export','system','print')[index]),compound='left',
            style='Sidebar.TRadiobutton',command=lambda:self.navigate(child))
        button.pack(fill='both',expand=True);button.bind('<Return>',lambda _:button.invoke())
        button.bind('<Enter>',lambda _:self.show_tip(button,title));button.bind('<Leave>',lambda _:self.hide_tip())
        button.bind('<FocusIn>',lambda _:self.show_tip(button,title));button.bind('<FocusOut>',lambda _:self.hide_tip())
        self.buttons.append(button)
    def navigate(self,page):
        self.hide_tip()
        was_expanded=self.expanded
        self.set_expanded(True)
        if str(page)==self.sections_page:
            if not was_expanded:self.sections_open=True
            elif self.select()==str(page):self.sections_open=not self.sections_open
            else:self.sections_open=True
        self.select(page);self.sync()
    def set_sections(self,sections,page):
        self.sections=sections;self.sections_page=str(page);self.sync()
    def set_expanded(self,expanded):
        self.cancel_motion()
        self.hide_tip();self.expanded=bool(expanded)
        width=196 if self.expanded else 44
        # The drawer overlays the page. Keeping its reserved rail width fixed
        # avoids reflowing forms when it opens, animates, or closes.
        self.bar.place_configure(width=width);self.bar.lift()
        self.sync()
    def toggle(self):self.set_expanded(not self.expanded)
    def cancel_leave(self,event=None):
        if event is not None and event.widget is not self:return
        if self.leave_job is not None:
            self.after_cancel(self.leave_job);self.leave_job=None
    def cancel_motion(self,event=None):
        if event is not None and event.widget is not self:return
        self.cancel_leave()
        if self.animation_job is not None:
            self.after_cancel(self.animation_job);self.animation_job=None
        self.closing=False
    def pointer_inside(self):
        x,y=self.winfo_pointerxy();left=self.bar.winfo_rootx();top=self.bar.winfo_rooty()
        return left<=x<left+self.bar.winfo_width() and top<=y<top+self.bar.winfo_height()
    def pointer_entered(self,event):
        if (self.closing or self.leave_job is not None) and self.pointer_inside():
            self.set_expanded(True)
    def pointer_left(self,event):
        # Leave also fires when moving between children. Check the whole rail
        # after the pointer settles, including category buttons and scrollbar.
        if not self.expanded or self.closing:return
        self.cancel_leave()
        self.leave_job=self.after(20,self.collapse_if_outside)
    def collapse_if_outside(self):
        self.leave_job=None
        if not self.expanded or not self.bar.winfo_ismapped():return
        if not self.pointer_inside():
            self.hide_tip();self.closing=True
            self.animation_start=time.monotonic();self.animation_width=self.bar.winfo_width()
            # Only the drawer changes width; the page keeps its geometry.
            self.bar.lift()
            self.animate_collapse()
    def animate_collapse(self):
        self.animation_job=None
        if not self.closing:return
        if self.pointer_inside():
            self.set_expanded(True);return
        # Leave room within half a second for Windows paint/event dispatch.
        # Time-based easing avoids accumulating delays between frames.
        progress=min(1.0,(time.monotonic()-self.animation_start)/.35)
        if progress>=1:
            self.set_expanded(False);return
        width=44+round((self.animation_width-44)*(1-progress)**3)
        self.bar.place_configure(width=width)
        self.animation_job=self.after(16,self.animate_collapse)
    def cycle(self,step=1):
        pages=self.tabs();start=self.index(self.select())
        for offset in range(1,len(pages)+1):
            page=pages[(start+step*offset)%len(pages)]
            if self.tab(page,'state')=='normal':self.select(page);break
        return 'break'
    def sync(self,*_):
        current=self.select();self.value.set(current)
        height=max(44,tkfont.Font(self,font=(FONT,12)).metrics('linespace')+20) if self.expanded else 44
        for slot in self.slots:slot.configure(height=height)
        visible=self.expanded and current==self.sections_page and self.sections_open
        for index,button in enumerate(self.buttons):
            title=self.titles[index]
            if str(self.tabs()[index])==self.sections_page:title+='  ▾' if visible else '  ▸'
            # Image-only rendering retains the text as the accessible control name.
            button.configure(text='  '+title,compound='left' if self.expanded else 'none',
                style='Sidebar.TRadiobutton' if self.expanded else 'Rail.TRadiobutton')
        if self.sections:
            if visible:self.sections.nav.pack(fill='both',expand=True,padx=(14,0),pady=(0,8))
            else:self.sections.nav.pack_forget()
    def show_tip(self,button,title):
        self.hide_tip()
        if self.expanded:return
        tip=tk.Toplevel(self);tip.wm_overrideredirect(True)
        ttk.Label(tip,text=title,style='Card.TLabel',padding=(10,6),relief='solid',borderwidth=1).pack()
        tip.geometry(f'+{button.winfo_rootx()+button.winfo_width()+8}+{button.winfo_rooty()}');self.tooltip=tip
    def hide_tip(self):
        if self.tooltip:
            self.tooltip.destroy();self.tooltip=None
    def tab(self,tab_id,option=None,**kwargs):
        result=super().tab(tab_id,option,**kwargs)
        if 'state' in kwargs:
            self.buttons[self.index(tab_id)].state(['disabled'] if kwargs['state']=='disabled' else ['!disabled'])
        return result


def nav_image(root,kind):
    """Small line icons only; large surfaces retain the v36 broad-fill tiles."""
    from PIL import Image,ImageDraw,ImageTk
    scale=3;image=Image.new('RGBA',(24*scale,24*scale));draw=ImageDraw.Draw(image)
    def line(points):draw.line([int(v*scale) for v in points],fill=PRIMARY,width=2*scale,joint='curve')
    if kind=='export':
        line((5,3,15,3,19,7,19,21,5,21,5,3));line((9,11,15,11));line((9,16,15,16))
    elif kind=='system':
        points=[]
        for tooth in range(8):
            for offset,radius in ((-.5,7.5),(-.25,10),(.25,10),(.5,7.5)):
                angle=(tooth+offset)*math.tau/8
                points.append(((12+radius*math.cos(angle))*scale,(12+radius*math.sin(angle))*scale))
        draw.polygon(points,fill=PRIMARY)
        draw.ellipse((6*scale,6*scale,18*scale,18*scale),fill=BG)
        draw.ellipse((8.5*scale,8.5*scale,15.5*scale,15.5*scale),outline=PRIMARY,width=2*scale)
    elif kind=='print':
        line((7,8,7,3,17,3,17,8));line((6,18,3,18,3,9,21,9,21,18,18,18));line((7,14,17,14,17,22,7,22,7,14))
    else:
        for y in (6,12,18):line((3,y,21,y))
    photo=ImageTk.PhotoImage(image.resize((18,18),Image.Resampling.LANCZOS),master=root)
    root.ui_images.append(photo);return photo


class StatusLabels:
    """Shared feedback state rendered on both independent settings pages."""
    def __init__(self,labels):self.labels=labels
    def configure(self,**kwargs):
        for label in self.labels:label.configure(**kwargs)
    config=configure
    def __getitem__(self,key):return self.labels[0][key]


class ModeTile(ttk.Radiobutton):
    """A real radio button, with a title, explanatory text and selection mark."""
    def __init__(self,parent,variable,value,title,detail):
        self.variable=variable;self.value=value
        super().__init__(parent,text=title+'\n'+detail,variable=variable,value=value,style='Choice.TRadiobutton',takefocus=True)
        self.title_label=tk.Label(self,text=title,font=(FONT,13,'bold'),anchor='w',borderwidth=0,cursor='hand2')
        self.detail_label=tk.Label(self,text=detail,font=(FONT,10),anchor='nw',justify='left',borderwidth=0,cursor='hand2')
        title_height=tkfont.Font(self,font=self.title_label['font']).metrics('linespace')+4
        detail_height=tkfont.Font(self,font=self.detail_label['font']).metrics('linespace')*2+4
        self.title_label.place(x=15,y=13,relwidth=1,width=-56,height=title_height)
        self.detail_label.place(x=15,y=title_height+16,relwidth=1,width=-30,height=detail_height)
        self.mark=tk.Canvas(self,width=24,height=24,highlightthickness=0,cursor='hand2');self.mark.place(relx=1,x=-38,y=14)
        for widget in (self.title_label,self.detail_label,self.mark):widget.bind('<Button-1>',lambda _:self.invoke())
        self.trace=variable.trace_add('write',self.refresh)
        self.bind('<Destroy>',self.cleanup,add='+');self.refresh()
    def cleanup(self,event):
        if event.widget==self:
            try:self.variable.trace_remove('write',self.trace)
            except tk.TclError:pass
    def refresh(self,*_):
        active=self.variable.get()==self.value;disabled=self.instate(['disabled'])
        bg='#EFF2F5' if disabled else LIGHT if active else SURFACE
        self.title_label.configure(background=bg,foreground=MUTED if disabled else '#006B7D' if active else INK)
        self.detail_label.configure(background=bg,foreground=MUTED)
        self.mark.configure(background=bg);self.mark.delete('all')
        self.mark.create_oval(3,3,21,21,outline=CONTROL if disabled or not active else PRIMARY,fill=PRIMARY if active and not disabled else bg)
        if active:self.mark.create_line(7,12,11,16,17,9,fill=SURFACE if not disabled else MUTED,width=1.6)
    def configure(self,cnf=None,**kwargs):
        result=super().configure(cnf,**kwargs)
        if hasattr(self,'title_label') and ('state' in kwargs or isinstance(cnf,dict) and 'state' in cnf):self.refresh()
        return result
    config=configure


class ScrollBody:
    def __init__(self,parent):
        host=ttk.Frame(parent);host.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(host,background=BG,highlightthickness=0,borderwidth=0)
        # Reserve the gutter even when its thumb is hidden. Changing viewport
        # width can rewrap labels and repeatedly show/hide a near-threshold bar.
        gutter=ttk.Frame(host,width=14);gutter.pack(side='right',fill='y');gutter.pack_propagate(False)
        self.scroll=ttk.Scrollbar(gutter,orient='vertical',command=self.canvas.yview)
        self.canvas.pack(side='left',fill='both',expand=True)
        def scrolling(first,last):
            self.scroll.set(first,last)
            visible=bool(self.scroll.winfo_manager())
            needed=not (float(first)<=0 and float(last)>=1)
            if visible and not needed:self.scroll.pack_forget()
            elif needed and not visible:self.scroll.pack(fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scrolling)
        self.body=ttk.Frame(self.canvas,padding=(0,0,4,8));self.window=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.window,width=e.width))

    def connect(self):
        def wheel(event):
            if self.canvas.yview()!=(0.0,1.0):self.canvas.yview_scroll(-int(event.delta/120),'units')
            return 'break'
        def focus(event):
            self.canvas.after_idle(lambda:self.reveal(event.widget))
        def bind(widget):
            if widget.winfo_class()!='Text':widget.bind('<MouseWheel>',wheel,add='+')
            widget.bind('<FocusIn>',focus,add='+')
            for child in widget.winfo_children():bind(child)
        bind(self.body)
        self.canvas.bind('<MouseWheel>',wheel)

    def reveal(self,widget):
        try:
            if not widget.winfo_exists() or not widget.winfo_ismapped():return
            top=widget.winfo_rooty()-self.body.winfo_rooty();bottom=top+widget.winfo_height()
            height=self.canvas.winfo_height();total=max(1,self.body.winfo_height())
            start=self.canvas.canvasy(0)
            if top<start+8:self.canvas.yview_moveto(max(0,(top-8)/total))
            elif bottom>start+height-8:self.canvas.yview_moveto((bottom-height+8)/total)
        except tk.TclError:pass


def card(parent,title=None,padding=20):
    edge=ttk.Frame(parent,style='Rounded.TFrame')
    body=ttk.Frame(edge,style='Card.TFrame',padding=(padding, max(0,padding-8)));body.pack(fill='both',expand=True,padx=8,pady=8)
    if title:ttk.Label(body,text=title,style='CardTitle.TLabel').pack(anchor='w',pady=(0,12))
    return edge,body


def hint(parent,text):
    label=ttk.Label(parent,text=text,style='Muted.TLabel',wraplength=400)
    label.pack(anchor='w',fill='x',pady=(0,6))
    parent.bind('<Configure>',lambda e:label.configure(wraplength=max(160,e.width-40)),add='+')
    return label


def check(parent,text,variable,detail=None):
    widget=ttk.Checkbutton(parent,text=text,variable=variable,style='Card.TCheckbutton')
    widget.pack(anchor='w',pady=(0,3))
    if detail:hint(parent,detail)
    return widget


def setting_row(parent,text,variable,detail=None):
    row=ttk.Frame(parent,style='Card.TFrame',padding=(0,15));row.pack(fill='x')
    control=ttk.Checkbutton(row,text=text,variable=variable,style='Switch.TCheckbutton',takefocus=True)
    control.pack(side='right',anchor='center',padx=(18,0))
    labels=ttk.Frame(row,style='Card.TFrame');labels.pack(side='left',fill='x',expand=True)
    title=ttk.Label(labels,text=text,style='CardTitle.TLabel',cursor='hand2');title.pack(anchor='w')
    labels.bind('<Configure>',lambda e:title.configure(wraplength=max(100,e.width)),add='+')
    title.bind('<Button-1>',lambda _:control.invoke())
    if detail:hint(labels,detail)
    ttk.Separator(parent).pack(fill='x')
    return control


class SectionBody(ScrollBody):
    """One settings category at a time; focus/reveal also switches hidden categories."""
    def __init__(self,parent,navigation):
        self.host=ttk.Frame(parent);self.host.pack(fill='both',expand=True)
        self.navigation=navigation;self.nav=ttk.Frame(navigation.bar)
        self.nav_scroll=ScrollBody(self.nav);self.nav_scroll.body.configure(padding=0)
        self.content=ttk.Frame(self.host);self.content.pack(side='left',fill='both',expand=True)
        self.sections=[];self.buttons=[];self.selected=tk.IntVar(value=0)
        super().__init__(self.content)
    def add(self,frame,title):
        index=len(self.sections);self.sections.append(frame)
        button=ttk.Radiobutton(self.nav_scroll.body,text=title,variable=self.selected,value=index,style='Subnav.TRadiobutton',command=lambda:self.select(index))
        button.pack(fill='x',pady=(0,4));self.buttons.append(button)
    def select(self,index):
        self.selected.set(index)
        for number,frame in enumerate(self.sections):
            if number==index:frame.pack(fill='x')
            else:frame.pack_forget()
        # Hidden startup pages do not need a nested repaint. A visible category
        # does need its new geometry before reveal() scrolls to a focused field.
        if self.canvas.winfo_ismapped():self.body.update_idletasks()
        self.canvas.yview_moveto(0)
        self.nav_scroll.reveal(self.buttons[index])
    def reveal(self,widget):
        parent=widget
        while parent is not None:
            if parent in self.sections:
                index=self.sections.index(parent)
                if index!=self.selected.get():self.select(index)
                break
            parent=getattr(parent,'master',None)
        super().reveal(widget)


def page_title(parent,title,description):
    top=ttk.Frame(parent);top.pack(fill='x',pady=(0,16))
    ttk.Label(top,text=title,style='PageTitle.TLabel').pack(anchor='w')
    description_label=ttk.Label(top,text=description,style='PageHint.TLabel');description_label.pack(anchor='w',pady=(3,0))
    top.bind('<Configure>',lambda e:description_label.configure(wraplength=max(200,e.width)))


def settings_footer(app,page,text,command):
    bar=ttk.Frame(page,padding=(0,12,0,0));bar.pack(side='bottom',fill='x')
    button=ttk.Button(bar,text=text,style='Save.TButton',command=command)
    button.pack(side='right',padx=(16,0))
    label=ttk.Label(bar,textvariable=app.settings_status,foreground=MUTED,wraplength=580)
    label.pack(side='left',fill='x',expand=True)
    bar.bind('<Configure>',lambda e:label.configure(wraplength=max(260,e.width-button.winfo_width()-24)))
    return button,label


def build(app):
    root=app.root;app.ui_style=theme(root)
    outer=ttk.Frame(root,padding=(16,18,16,12));outer.pack(fill='both',expand=True)
    footer=ttk.Frame(outer);footer.pack(side='bottom',fill='x',pady=(12,0))
    ttk.Label(footer,text=f'版本 {APP_VERSION}',foreground=MUTED,font=(FONT,10)).pack(side='left')
    ttk.Label(footer,textvariable=app.db_status,font=(FONT,10)).pack(side='right')
    app.db_lamp=tk.Canvas(footer,width=18,height=18,background=BG,highlightthickness=0)
    app.db_lamp.pack(side='right',padx=5);app.lamp_circle=app.db_lamp.create_oval(4,4,14,14,fill='#929baa',outline='')
    app.tabs=Navigation(outer);app.tabs.pack(side='left',fill='both',expand=True);app.tabs.enable_traversal()
    root.bind('<Control-b>',lambda _:app.tabs.toggle())
    root.bind('<Control-Tab>',lambda _:app.tabs.cycle())
    root.bind('<Control-Shift-Tab>',lambda _:app.tabs.cycle(-1))
    app.export_page=ttk.Frame(app.tabs,padding=(0,8,0,0));app.system_page=ttk.Frame(app.tabs,padding=(0,8,0,0));app.print_page=ttk.Frame(app.tabs,padding=(0,8,0,0))
    for page,title in [(app.export_page,'匯出工作簿'),(app.system_page,'系統設定'),(app.print_page,'列印設定')]:app.tabs.add(page,text=title)
    app.settings_page=app.system_page  # Existing error routes point directly at system settings.
    build_export(app)
    system_status=build_system(app);print_status=build_print(app)
    app.settings_status_label=StatusLabels([system_status,print_status])


def build_export(app):
    page=app.export_page
    page_title(page,'每日工作簿','選擇工作日期與拆併單方式，完成後自動開啟 PDF。')
    area=ScrollBody(page);app.export_scroll=area
    edge,form=card(area.body,padding=20);edge.pack(fill='x')
    form.columnconfigure(0,weight=1)
    date_line=ttk.Frame(form,style='Card.TFrame');date_line.pack(fill='x')
    left=ttk.Frame(date_line,style='Card.TFrame');left.pack(side='left')
    ttk.Label(left,text='工作日期',style='CardTitle.TLabel').pack(anchor='w',pady=(0,8))
    fields=ttk.Frame(left,style='Card.TFrame');fields.pack(anchor='w')
    app.date_picker=DatePicker(fields,app.date);app.date_picker.configure(style='Card.TFrame');app.date_picker.pack(side='left');app.date_entry=app.date_picker.entry
    ttk.Button(fields,text='今天',command=lambda:app.date.set(dt.date.today().isoformat())).pack(side='left',padx=(8,0))
    app.layout_description=tk.StringVar()
    def describe(*_):app.layout_description.set('A4 直式\n每頁 20 筆' if app.fixed_20_rows.get() else 'A4 直式\n依內容自動列高')
    app.fixed_20_rows.trace_add('write',describe);describe()
    badge=ttk.Label(date_line,textvariable=app.layout_description,style='Badge.TLabel',justify='right',padding=(12,8));badge.pack(side='right',anchor='s',pady=5)
    date_stacked=None
    def arrange_date(event):
        nonlocal date_stacked
        stacked=event.width<left.winfo_reqwidth()+badge.winfo_reqwidth()+16
        if stacked==date_stacked:return
        date_stacked=stacked
        left.pack_configure(side='top' if stacked else 'left',anchor='w')
        badge.pack_configure(side='top' if stacked else 'right',anchor='w' if stacked else 's',pady=(12,0) if stacked else 5)
    date_line.bind('<Configure>',arrange_date)
    mode_line=ttk.Frame(form,style='Card.TFrame');mode_line.pack(fill='x',pady=(18,0))
    ttk.Label(mode_line,text='檢驗單處理方式',style='CardTitle.TLabel').pack(anchor='w',pady=(0,8))
    choices=ttk.Frame(mode_line,style='Card.TFrame');choices.pack(fill='x')
    app.mode_buttons=[]
    for index,(value,title,detail) in enumerate([('split','拆單','每張檢驗單\n分開列印'),('merge','併單','合併項目\n保留全部工作號'),('merge_first','併單（首號）','合併項目\n只印第一個工作號')]):
        choices.columnconfigure(index,weight=1,uniform='modes')
        button=ModeTile(choices,app.order_mode,value,title,detail)
        button.grid(row=0,column=index,sticky='nsew',padx=(0,10 if index<2 else 0));app.mode_buttons.append(button)
    mode_columns=None
    def arrange_modes(event):
        nonlocal mode_columns
        # Keep labels at their readable size when the expanded sidebar narrows
        # the viewport. Stack complete choices instead of clipping their text.
        minimum=max(b.title_label.winfo_reqwidth()+60 for b in app.mode_buttons)
        columns=3 if event.width>=minimum*3+20 else 1
        if columns==mode_columns:return
        mode_columns=columns
        for index,button in enumerate(app.mode_buttons):
            choices.columnconfigure(index,weight=1 if index<columns else 0,uniform='modes' if columns==3 else '')
            button.grid_configure(row=0 if columns==3 else index,column=index if columns==3 else 0,
                padx=(0,10 if columns==3 and index<2 else 0),pady=(0,8 if columns==1 and index<2 else 0))
    choices.bind('<Configure>',arrange_modes)
    ttk.Separator(form).pack(fill='x',pady=(18,14))
    actions=ttk.Frame(form,style='Card.TFrame');actions.pack(fill='x')
    app.submit_button=ttk.Button(actions,text='送出並產生 PDF',style='Primary.TButton',command=app.submit)
    app.submit_button.pack(anchor='center',ipadx=24)
    app.status_label=ttk.Label(area.body,textvariable=app.status,wraplength=900,font=(FONT,10),foreground=MUTED)
    app.status_label.pack(anchor='w',pady=(6,6))
    area.body.bind('<Configure>',lambda e:app.status_label.configure(wraplength=max(200,e.width-8)),add='+')
    edge,result=card(area.body,padding=18);edge.configure(height=166);edge.pack(fill='x');edge.pack_propagate(False)
    tools=ttk.Frame(result,style='Card.TFrame');tools.pack(side='bottom',fill='x',pady=(8,0))
    app.open_button=ttk.Button(tools,text='開啟 PDF',command=app.open_pdf,state='disabled');app.open_button.pack(side='left',padx=(0,8))
    app.folder_button=ttk.Button(tools,text='開啟輸出資料夾',command=app.open_output);app.folder_button.pack(side='left')
    ttk.Label(result,text='輸出結果',style='CardTitle.TLabel').pack(anchor='w',pady=(0,8))
    holder=ttk.Frame(result,style='Card.TFrame');holder.pack(fill='both',expand=True)
    icon(holder,size=30,color=MUTED).pack(side='left',padx=(0,12),anchor='n')
    app.result_label=tk.Text(holder,height=1,width=1,wrap='word',borderwidth=0,highlightthickness=0,
        background=SURFACE,foreground=MUTED,font=(FONT,11),state='disabled',takefocus=True)
    app.result_label.pack(side='left',fill='both',expand=True)
    scroll=ttk.Scrollbar(holder,orient='vertical',command=app.result_label.yview)
    def scrolled(first,last):
        scroll.set(first,last)
        if float(first)<=0 and float(last)>=1:scroll.pack_forget()
        else:scroll.pack(side='right',fill='y')
    app.result_label.configure(yscrollcommand=scrolled)
    app.result_text.trace_add('write',app.refresh_result);app.refresh_result()
    area.connect()


def build_system(app):
    page=app.system_page
    app.save_button,label=settings_footer(app,page,'儲存系統設定',app.save_system_preferences)
    page_title(page,'系統設定','設定資料來源、輸出位置，或帶入上一版的設定。')
    area=ScrollBody(page);app.system_scroll=area;app.system_canvas=area.canvas
    edge,body=card(area.body,'檔案與連線');edge.pack(fill='x',pady=(0,16))
    rows=ttk.Frame(body,style='Card.TFrame');rows.pack(fill='x');rows.columnconfigure(1,weight=1)
    for row,title,var,command in [(0,'Access 資料庫',app.db,app.choose_db),(1,'輸出資料夾',app.output_dir,app.choose_output)]:
        ttk.Label(rows,text=title,style='Card.TLabel').grid(row=row,column=0,sticky='w',padx=(0,16),pady=8)
        entry=ttk.Entry(rows,textvariable=var);entry.grid(row=row,column=1,sticky='ew',pady=8)
        ttk.Button(rows,text='瀏覽…',command=command).grid(row=row,column=2,padx=(8,0),pady=8)
    actions=ttk.Frame(body,style='Card.TFrame');actions.pack(fill='x',pady=(8,0))
    app.connection_button=ttk.Button(actions,text='測試連線',command=app.test_connection);app.connection_button.pack(side='left')
    app.tools_toggle=ttk.Button(actions,text='連線工具 ▾',command=app.toggle_connection_tools);app.tools_toggle.pack(side='right')
    app.connection_tools=ttk.Frame(body,style='Card.TFrame')
    app.repair_button=ttk.Button(app.connection_tools,text='安裝 Access 元件',command=app.install_access_component,state='disabled');app.repair_button.pack(side='left')
    app.diagnostic_button=ttk.Button(app.connection_tools,text='匯出連線診斷',command=app.export_connection_diagnostic);app.diagnostic_button.pack(side='left',padx=8)
    edge,body=card(area.body,'匯入設定及匯出設定');edge.pack(fill='x')
    hint(body,'可從舊版程式資料夾或已匯出的設定資料夾匯入，也可匯出全部設定供日後使用。')
    app.import_system=tk.BooleanVar(value=True)
    check(body,'匯入時一併沿用系統設定',app.import_system,'包含資料庫、輸出位置與拆併單偏好；匯入前會先備份。')
    actions=ttk.Frame(body,style='Card.TFrame');actions.pack(anchor='w',pady=(8,0))
    app.import_previous_button=ttk.Button(actions,text='匯入設定',command=app.import_previous_settings);app.import_previous_button.pack(side='left')
    ttk.Button(actions,text='匯出設定',command=app.backup_settings).pack(side='left',padx=8)
    edge,body=card(area.body,'程式更新');edge.pack(fill='x',pady=(16,0))
    ttk.Label(body,textvariable=app.update_status,style='Card.TLabel',wraplength=570).pack(anchor='w',pady=(0,8))
    hint(body,'從 GitHub Release 下載新版；更新時保留本機系統、列印設定與資料。')
    actions=ttk.Frame(body,style='Card.TFrame');actions.pack(anchor='w',pady=(8,0))
    app.update_button=ttk.Button(actions,text='檢查並更新程式',command=app.check_updates)
    app.update_button.pack(side='left')
    import webbrowser
    from .updates import RELEASES_URL
    ttk.Button(actions,text='開啟版本下載頁',command=lambda:webbrowser.open(RELEASES_URL)).pack(side='left',padx=8)
    area.connect()
    return label


def build_print(app):
    page=app.print_page
    app.print_save_button,label=settings_footer(app,page,'儲存列印設定',lambda:app.save_preferences(False,scope='print'))
    page_title(page,'列印設定','由整頁版面、欄位與每筆資料，逐步設定到個別項目。')
    area=SectionBody(page,app.tabs);app.print_scroll=area;app.settings_canvas=area.canvas
    cards=[]
    def section(title):
        edge,body=card(area.body,title);cards.append(edge);area.add(edge,title)
        return body
    body=section('頁面版面')
    hint(body,'設定每頁的內容與填寫空間。')
    setting_row(body,'每張 A4 固定 20 筆',app.fixed_20_rows,'取消後，依內容加高每筆並自動換頁。')
    setting_row(body,'列印欄位標頭',app.show_headers,'在每頁顯示診所、工作號及各檢驗區標頭。')
    setting_row(body,'以淡灰線區隔列印區域',app.show_region_lines,'在檢驗區之間加入淡灰色分隔線。')
    setting_row(body,'頁首加入 Glucose AC&PC 填入格',app.export_glucose_ac,'有 AC 或 PC 就列一格；兩項都有也只列一格。5 列 × 5 欄，直排接下頁。')
    body=section('欄位與分區')
    hint(body,'先設定各欄字體，再安排檢驗區內的子區域、空位遞補與自動起始區。')
    app.font_button=ttk.Button(body,text='列印字體設定',command=app.font_editor)
    app.font_button.pack(fill='x',pady=(8,8))
    hint(body,'分別調整工作號、就醫日期、姓名及各檢驗區的字體大小。')
    app.subregion_button=ttk.Button(body,text='子區域與自動起始區',command=lambda:app.catalog_editor('subregions'))
    app.subregion_button.pack(fill='x',pady=(12,8))
    hint(body,'設定子區域的顯示方式、空區與位置遞補，以及生化自動項目的起始區。')
    from . import print_style as ps
    ttk.Separator(body).pack(fill='x',pady=(16,12))
    ttk.Label(body,text='機器流水號',style='CardTitle.TLabel').pack(anchor='w')
    setting_row(body,'流水號使用上標',app.serial_superscript,'未勾選時，流水號與項目名稱使用相同基準線。')
    row=ttk.Frame(body,style='Card.TFrame');row.pack(fill='x',pady=8)
    ttk.Label(row,text='流水號字級',style='Card.TLabel').pack(side='left')
    app.serial_size_input=ttk.Spinbox(row,from_=6,to=24,increment=.5,width=5,textvariable=app.serial_font_size)
    app.serial_size_input.pack(side='left',padx=8);ttk.Label(row,text='pt',style='Card.TLabel').pack(side='left')
    colors=ttk.Frame(body,style='Card.TFrame');colors.pack(fill='x',pady=4);colors.columnconfigure(1,weight=1)
    app.serial_color_inputs={}
    for index,(key,title) in enumerate((('e411','e411'),('hba1c','HbA1c'),('mab','mab'))):
        ttk.Label(colors,text=title+' 流水號顏色',style='Card.TLabel').grid(row=index,column=0,sticky='w',padx=(0,12),pady=5)
        values=[name for name in ps.PALETTE if name!='自動']
        if app.serial_colors[key].get() not in values:values.append(app.serial_colors[key].get())
        entry=ttk.Combobox(colors,textvariable=app.serial_colors[key],values=values,state='readonly',width=12)
        entry.grid(row=index,column=1,sticky='ew',pady=5);app.serial_color_inputs[key]=entry
    hint(body,'字級為目標大小；空間不足時配合該格縮小。項目文字的配色規則不影響流水號。')
    body=section('併單與同上符號')
    hint(body,'決定哪些原單獨立保留，以及連續資料重複時如何顯示。')
    ttk.Label(body,text='併單排除',style='CardTitle.TLabel').pack(anchor='w',pady=(8,0))
    setting_row(body,'指定工作號不併單',app.merge_exclusions_enabled,'這些檢驗單各自保留一筆，不併入其他工作號。')
    ttk.Label(body,text='工作號（以逗號分隔）',style='Card.TLabel').pack(anchor='w',pady=(8,4))
    app.merge_exclusions_input=ttk.Entry(body,textvariable=app.merge_excluded_worknos)
    app.merge_exclusions_input.pack(fill='x',pady=(0,8))
    hint(body,'預設 9, 10, 69, 70, 129, 130；前置零視為同一工作號，拆單模式不受影響。')
    ttk.Label(body,text='重複內容顯示',style='CardTitle.TLabel').pack(anchor='w',pady=(20,0))
    setting_row(body,'同頁生化／糞便相同時印「〃」',app.ditto_bio,'與前一筆的生化內容完全相同時使用。')
    setting_row(body,'同頁同病患姓名印「〃」',app.ditto_patient,'性別、病歷號留白；就醫日期與保險註記保留。')
    setting_row(body,'同上符號保留 @',app.ditto_keep_adult,'@ 不參與生化同上比對，且有 @ 時仍顯示；只有 @ 時不加同上符號。')
    row=ttk.Frame(body,style='Card.TFrame');row.pack(anchor='w',pady=(8,0))
    ttk.Label(row,text='符號字級',style='Card.TLabel').pack(side='left')
    app.ditto_size_input=ttk.Spinbox(row,from_=6,to=24,increment=.5,width=5,textvariable=app.ditto_font_size)
    app.ditto_size_input.pack(side='left',padx=8);ttk.Label(row,text='pt',style='Card.TLabel').pack(side='left')
    ttk.Checkbutton(row,text='加粗',variable=app.ditto_bold,style='Card.TCheckbutton').pack(side='left',padx=(16,0))
    row=ttk.Frame(body,style='Card.TFrame');row.pack(anchor='w',pady=(12,0))
    ttk.Label(row,text='符號位置',style='Card.TLabel').pack(side='left')
    app.ditto_alignment_input=ttk.Combobox(row,textvariable=app.ditto_alignment,values=list(ps.DITTO_ALIGN.values()),state='readonly',width=9)
    app.ditto_alignment_input.pack(side='left',padx=8)
    from . import print_style as ps
    body=section('併單來源配色')
    hint(body,'同一筆併單內，依項目來自第幾張原始檢驗單設定顏色。')
    setting_row(body,'併單依原始單別變色',app.merged_color_enabled)
    row=ttk.Frame(body,style='Card.TFrame');row.pack(fill='x',pady=(4,10));row.columnconfigure(1,weight=1)
    app.merged_color_inputs=[]
    for index,title in enumerate(('第 1 張','第 2 張','第 3 張','第 4 張起')):
        ttk.Label(row,text=title,style='Card.TLabel').grid(row=index,column=0,sticky='w',padx=(0,10),pady=4)
        entry=ttk.Combobox(row,textvariable=app.merged_order_colors[index],values=[k for k in ps.PALETTE if k!='自動'],width=12)
        entry.grid(row=index,column=1,sticky='ew',pady=4);app.merged_color_inputs.append(entry)
        ttk.Button(row,text='選色',width=6,command=lambda i=index:app.choose_merged_color(i)).grid(row=index,column=2,padx=(8,0),pady=4)
    hint(body,'按工作號由小到大；重複項目採最早出現那張單的顏色。')
    hint(body,'配色規則優先，其次為項目指定色、併單色。流水號維持原色。')
    body=section('項目列印與簡稱')
    from .help_tip import help_icon
    actions=ttk.Frame(body,style='Card.TFrame');actions.pack(fill='x',pady=(8,0))
    ttk.Button(actions,text='套組、單項、診所設定',command=lambda:app.catalog_editor('items')).pack(side='left',fill='x',expand=True,pady=(0,8))
    help_icon(actions,'設定是否列印、列印代碼、區域、位置、流水號分組與診所簡稱，也可查找套組子項。黃色列為尚未儲存的修改；可一次儲存全部。').pack(side='left',padx=8)
    check(body,'機器分組已核對（隱藏待核對提示）',app.confirmed)
    ttk.Separator(body).pack(fill='x',pady=(16,12))
    heading=ttk.Frame(body,style='Card.TFrame');heading.pack(fill='x')
    ttk.Label(heading,text='清單資料與 JSON 設定',style='CardTitle.TLabel').pack(side='left')
    help_icon(heading,lambda:app.catalog_help.get()).pack(side='left',padx=8)
    app.catalog_info=tk.StringVar(value='尚未載入清單')
    app.catalog_help=tk.StringVar(value='清單只含診所、套組及單項字典，不含病患資料。匯入只套用設定，不更改資料庫路徑。新增來源項目後可從資料庫更新清單。')
    metadata=ttk.Label(body,textvariable=app.catalog_info,style='Muted.TLabel',wraplength=620)
    metadata.pack(anchor='w',fill='x',pady=(8,12))
    body.bind('<Configure>',lambda e:metadata.configure(wraplength=max(200,e.width-40)),add='+')
    actions=ttk.Frame(body,style='Card.TFrame');actions.pack(fill='x')
    app.catalog_update_button=ttk.Button(actions,text='從資料庫更新清單',command=lambda:app.catalog_editor(None,refresh=True))
    app.catalog_export_button=ttk.Button(actions,text='匯出 JSON',command=lambda:app.catalog_editor('export_json'))
    app.catalog_import_button=ttk.Button(actions,text='匯入 JSON',command=lambda:app.catalog_editor('import_json'))
    app.catalog_tools=[app.catalog_update_button,app.catalog_export_button,app.catalog_import_button]
    for column,button in enumerate(app.catalog_tools):
        actions.columnconfigure(column,weight=1);button.grid(row=0,column=column,sticky='ew',padx=(0,8) if column<2 else 0)
    body=section('項目對應顏色')
    app.color_rule_button=ttk.Button(body,text='列印代碼配色規則',command=app.color_rule_editor)
    app.color_rule_button.pack(anchor='w',pady=(0,8))
    hint(body,'以列印代碼和適用區域設定配色規則，例如 CBC 區的 CBC、Plt、WBC、Hb 印紅字。')
    hint(body,'規則優先於項目個別顏色及併單顏色；流水號維持原色。')
    area.select(0);app.print_cards=cards;area.connect();area.nav_scroll.connect();app.tabs.set_sections(area,page)
    area.selected.trace_add('write',lambda *_:app.catalog_editor('summary') if area.selected.get()==4 and area.canvas.winfo_ismapped() else None)
    return label
