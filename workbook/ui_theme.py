"""Native, accessible controls styled from the v34 ImageGen design concept."""
import tkinter as tk
from tkinter import ttk
from PIL import Image,ImageDraw,ImageTk

BG='#F6F8FA'
SURFACE='#FFFFFF'
INK='#152C43'
MUTED='#5C6E82'
LINE='#DFE7ED'
CONTROL='#B9C8D3'
PRIMARY='#007F92'
LIGHT='#E7F5F6'
FONT='Microsoft JhengHei UI'


def theme(root):
    style=ttk.Style(root);style.theme_use('clam');root.configure(background=BG)
    style.configure('.',font=(FONT,12),background=BG,foreground=INK)
    for name,bg in [('TFrame',BG),('Card.TFrame',SURFACE)]:style.configure(name,background=bg)
    for name,bg,fg,size,weight in [('TLabel',BG,INK,12,'normal'),('Card.TLabel',SURFACE,INK,12,'normal'),
        ('Muted.TLabel',SURFACE,MUTED,10,'normal'),('PageHint.TLabel',BG,MUTED,10,'normal'),
        ('Heading.TLabel',SURFACE,INK,16,'bold'),('CardTitle.TLabel',SURFACE,INK,13,'bold'),
        ('PageTitle.TLabel',BG,INK,20,'bold'),('Badge.TLabel','#EEF3F7',MUTED,10,'normal')]:
        style.configure(name,background=bg,foreground=fg,font=(FONT,size,weight))
    root.ui_images=[]
    def tile(fill,border,bg=BG,radius=7):
        # ttk replicates the centre/edge pixels (it does not scale a nine-slice).
        # An 8px centre caused thousands of Windows image draws per large card.
        # Keep the original corners and minimum size, but use a broad fill tile.
        size=128;scale=3
        img=Image.new('RGB',(size*scale,size*scale),bg);d=ImageDraw.Draw(img)
        d.rounded_rectangle((1,1,size*scale-2,size*scale-2),radius=radius*scale,fill=fill,outline=border,width=scale)
        photo=ImageTk.PhotoImage(img.resize((size,size),Image.Resampling.LANCZOS),master=root)
        root.ui_images.append(photo);return photo
    def box(element,fill,border,hover,pressed,disabled,focus,selected=None):
        states=[('disabled',tile(disabled,LINE)),('pressed',tile(pressed,border)),('focus',tile(fill,focus)),('active',tile(hover,focus))]
        if selected:
            states.insert(1,('selected',tile(selected,PRIMARY)))
            states.insert(1,('selected','focus',tile(selected,'#004B59')))
        style.element_create(element,'image',tile(fill,border),*states,border=8,width=24,height=24,sticky='nsew')
    button_layout=lambda element:[(element,{'sticky':'nsew','children':[('Button.padding',{'sticky':'nsew','children':[('Button.label',{'sticky':'nsew'})]})]})]
    box('Soft.border',SURFACE,CONTROL,'#F0F7F8','#DFEFF2','#EFF2F5',PRIMARY)
    style.layout('TButton',button_layout('Soft.border'))
    style.configure('TButton',padding=(14,9),font=(FONT,12),anchor='center',foreground=INK,width=0)
    style.map('TButton',foreground=[('disabled','#8594A3')])
    box('Action.border',PRIMARY,PRIMARY,'#007789','#006B7D','#ACCBD0','#004B59')
    for name in ('Primary.TButton','Save.TButton'):
        style.layout(name,button_layout('Action.border'))
        style.configure(name,padding=(22,11),foreground=SURFACE,font=(FONT,12,'bold'),anchor='center')
        style.map(name,foreground=[('disabled','#F3F8F9'),('!disabled',SURFACE)])
    style.configure('Quiet.TButton',padding=(12,8),font=(FONT,10))
    style.configure('Table.TButton',padding=(10,3),font=(FONT,11))
    style.configure('Batch.Save.TButton',padding=(16,6),font=(FONT,12,'bold'))
    box('Card.border',SURFACE,LINE,SURFACE,SURFACE,SURFACE,LINE)
    style.layout('Rounded.TFrame',[('Card.border',{'sticky':'nsew'})])
    style.configure('Rounded.TFrame',background=BG)
    style.configure('TEntry',font=(FONT,11),padding=(10,8),fieldbackground=SURFACE,
        bordercolor=CONTROL,lightcolor=SURFACE,darkcolor=SURFACE,insertcolor=INK)
    style.map('TEntry',bordercolor=[('focus',PRIMARY)],lightcolor=[('focus',PRIMARY)],darkcolor=[('focus',PRIMARY)],fieldbackground=[('readonly',SURFACE)])
    style.configure('TCombobox',padding=(9,6),arrowsize=15,font=(FONT,12),fieldbackground=SURFACE,background=SURFACE,bordercolor=CONTROL,lightcolor=SURFACE,darkcolor=SURFACE)
    style.map('TCombobox',fieldbackground=[('readonly',SURFACE)],selectbackground=[('readonly',SURFACE)],selectforeground=[('readonly',INK)],bordercolor=[('focus',PRIMARY)])
    style.map('Pending.TCombobox',fieldbackground=[('readonly','#FFF0AD')],selectbackground=[('readonly','#FFF0AD')])
    style.configure('TSpinbox',padding=(8,7),arrowsize=13,fieldbackground=SURFACE,bordercolor=CONTROL,lightcolor=SURFACE,darkcolor=SURFACE)
    style.map('TSpinbox',bordercolor=[('focus',PRIMARY)])
    for base in ('TCheckbutton','TRadiobutton'):
        style.configure(base,padding=(0,6),focuscolor=PRIMARY)
        style.configure('Card.'+base,background=SURFACE,padding=(0,6),focuscolor=PRIMARY)
        style.map('Card.'+base,background=[('active',SURFACE)],foreground=[('disabled',MUTED)])
    # Toggle images keep standard ttk Checkbutton keyboard/state semantics.
    def toggle(on,disabled=False):
        img=Image.new('RGB',(44*3,24*3),SURFACE);d=ImageDraw.Draw(img)
        fill=('#BCD1D5' if on else '#E0E6EB') if disabled else (PRIMARY if on else '#B9C7D1')
        d.rounded_rectangle((0,0,131,71),radius=36,fill=fill)
        x=23 if on else 3;d.ellipse((x*3,9,(x+18)*3,63),fill=SURFACE)
        photo=ImageTk.PhotoImage(img.resize((44,24),Image.Resampling.LANCZOS),master=root);root.ui_images.append(photo);return photo
    style.element_create('Switch.indicator','image',toggle(False),('disabled','selected',toggle(True,True)),('disabled',toggle(False,True)),('selected',toggle(True)))
    style.layout('Switch.TCheckbutton',[('Checkbutton.focus',{'sticky':'nswe','children':[('Switch.indicator',{'sticky':'nswe'})]})])
    style.configure('Switch.TCheckbutton',background=SURFACE,padding=4,focuscolor=PRIMARY)
    box('Choice.border',SURFACE,LINE,SURFACE,LIGHT,'#EFF2F5',PRIMARY,LIGHT)
    style.layout('Choice.TRadiobutton',button_layout('Choice.border'))
    style.configure('Choice.TRadiobutton',padding=(14,17),font=(FONT,12),anchor='w',justify='left')
    # Keep the native radio label for sizing/accessibility; ModeTile overlays
    # the visible title and description at their own readable font sizes.
    style.map('Choice.TRadiobutton',foreground=[('disabled','#EFF2F5'),('selected',LIGHT),('!selected',SURFACE)])
    box('Section.border',BG,BG,'#EEF3F6',LIGHT,BG,PRIMARY,LIGHT)
    style.layout('Section.TRadiobutton',button_layout('Section.border'))
    style.configure('Section.TRadiobutton',padding=(13,12),font=(FONT,12),anchor='w')
    style.map('Section.TRadiobutton',foreground=[('selected','#006D7F'),('!selected',MUTED)])
    for name,padding,size in [('Sidebar.TRadiobutton',(10,2),12),('Rail.TRadiobutton',(5,5),12),('Subnav.TRadiobutton',(10,4),11)]:
        style.layout(name,button_layout('Section.border'))
        style.configure(name,padding=padding,font=(FONT,size),anchor='w' if name!='Rail.TRadiobutton' else 'center')
        style.map(name,foreground=[('disabled',CONTROL),('selected','#006D7F'),('!selected',MUTED)])
    for name,padding,anchor in [('Menu.TButton',(5,5),'center'),('SidebarMenu.TButton',(10,2),'w')]:
        style.layout(name,button_layout('Section.border'))
        style.configure(name,padding=padding,width=0,font=(FONT,12),anchor=anchor)
    # Top-level tabs remain a real notebook with keyboard traversal.
    nav=tk.PhotoImage(master=root,width=128,height=24);nav.put(BG,to=(0,0,128,24));root.ui_images.append(nav)
    selected=tk.PhotoImage(master=root,width=128,height=24);selected.put(BG,to=(0,0,128,24));selected.put(PRIMARY,to=(0,22,128,24));root.ui_images.append(selected)
    style.element_create('Nav.background','image',nav,('selected',selected),('focus',tile(BG,PRIMARY)),border=2,width=8,height=8,sticky='nsew')
    style.layout('Nav.TRadiobutton',button_layout('Nav.background'))
    style.configure('Nav.TRadiobutton',padding=(20,11),font=(FONT,12,'bold'),anchor='center')
    style.map('Nav.TRadiobutton',foreground=[('disabled',CONTROL),('selected',PRIMARY),('!selected',MUTED)])
    style.configure('TNotebook',background=BG,borderwidth=0,tabmargins=(0,0,0,10))
    style.layout('TNotebook.Tab',[('Notebook.padding',{'sticky':'nswe','children':[('Notebook.label',{'sticky':'nswe'})]})])
    style.configure('TNotebook.Tab',padding=(20,11),font=(FONT,11,'bold'),foreground=MUTED)
    style.map('TNotebook.Tab',background=[('selected',LIGHT),('active','#EFF5F6')],foreground=[('selected',PRIMARY)])
    style.layout('Main.TNotebook',[]);style.layout('Main.TNotebook.Tab',[])
    style.configure('Main.TNotebook',tabmargins=0,borderwidth=0)
    style.configure('TScrollbar',background='#CCD7DF',troughcolor=BG,borderwidth=0,arrowsize=12,gripcount=0)
    style.map('TScrollbar',background=[('active','#98B4C0'),('pressed','#829EAC')])
    hairline=tk.PhotoImage(master=root,width=128,height=128);hairline.put(LINE,to=(0,0,128,128));root.ui_images.append(hairline)
    style.element_create('Hairline','image',hairline,border=0,width=1,height=1,sticky='nsew')
    style.layout('TSeparator',[('Hairline',{'sticky':'nsew'})]);style.configure('TSeparator',background=LINE)
    root.option_add('*TCombobox*Listbox.font',(FONT,11));root.option_add('*TCombobox*Listbox.selectBackground',LIGHT);root.option_add('*TCombobox*Listbox.selectForeground',INK)
    return style


def icon(parent,kind='document',size=30,background=SURFACE,color=PRIMARY):
    canvas=tk.Canvas(parent,width=size,height=size,highlightthickness=0,background=background,takefocus=False)
    s=size/32
    if kind=='document':
        canvas.create_line(*[v*s for v in (9,5,20,5,25,10,25,28,9,28,9,5)],fill=color,width=1.7)
        canvas.create_line(*[v*s for v in (20,5,20,11,25,11)],fill=color,width=1.7)
        for y in (16,21):canvas.create_line(13*s,y*s,21*s,y*s,fill=color,width=1.5)
    return canvas
