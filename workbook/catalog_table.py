"""Column filters and natural sorting over the local, non-patient dictionary."""
import re

ALL='全部'
EMPTY='（空白）'
NONEMPTY='（非空白）'
ENUM_COLUMNS={'kind','zone','group','print_state','subregion_display','position_display','display','compact_subregions','compact_positions'}


def natural_key(value):
    return tuple((0,int(part)) if part.isdigit() else (1,part.casefold())
                 for part in re.split(r'(\d+)',str(value)))


def select_rows(rows,query='',filters=None,column=None,descending=False):
    query=query.strip().casefold();filters=filters or {}
    found=[]
    for index,row in enumerate(rows):
        if query and query not in ' '.join(str(row.get(k) or '') for k in
                ('key','kind','code','nhi','name','zone','label','group','search','print_state','subregion_display','position_display')).casefold():continue
        for key,wanted in filters.items():
            wanted=wanted.strip();actual=str(row.get(key) or '')
            if not wanted or wanted==ALL:continue
            if wanted==EMPTY:matches=not actual.strip()
            elif wanted==NONEMPTY:matches=bool(actual.strip())
            elif key in ENUM_COLUMNS:matches=actual==wanted
            else:matches=wanted.casefold() in actual.casefold()
            if not matches:break
        else:found.append((index,row))
    if column:
        filled=[r for r in found if str(r[1].get(column) or '').strip()]
        blank=[r for r in found if not str(r[1].get(column) or '').strip()]
        filled.sort(key=lambda r:natural_key(r[1].get(column)),reverse=descending)
        found=filled+blank  # Missing codes stay at the end in either direction.
    return found


class CatalogTable:
    def __init__(self,parent,columns,on_select,help_text=None,*,hierarchy=False):
        import tkinter as tk
        from tkinter import ttk
        from .ui_styles import readable_table
        self.columns=columns;self.rows=[];self.column=None;self.descending=False;self.hierarchy=hierarchy
        self.on_select=on_select;self.filters={};self.filter_widgets={};self.cells=[];self.headers={};self.suspend=False
        self.query=tk.StringVar();self.count=tk.StringVar()
        search=ttk.Frame(parent);search.pack(fill='x',pady=(0,6))
        ttk.Label(search,text='搜尋全部欄位').pack(side='left')
        from .help_tip import help_icon
        help_icon(search,help_text or '各欄可分別篩選；點上方欄名可排序，再點一次反向。黃色列代表尚未儲存的修改。').pack(side='left',padx=4)
        self.search_entry=ttk.Entry(search,textvariable=self.query);self.search_entry.pack(side='left',fill='x',expand=True,padx=10)
        ttk.Button(search,text='清除全部篩選',style='Table.TButton',command=self.clear_filters).pack(side='right')
        ttk.Label(parent,textvariable=self.count).pack(side='bottom',anchor='w',pady=(6,0))
        holder=ttk.Frame(parent);holder.pack(fill='both',expand=True)
        holder.columnconfigure(0,weight=1);holder.rowconfigure(1,weight=1)
        self.canvas=tk.Canvas(holder,height=60,highlightthickness=0,background='#f4f6fa')
        self.canvas.grid(row=0,column=0,sticky='ew')
        self.filter_frame=ttk.Frame(self.canvas,height=60)
        self.filter_window=self.canvas.create_window(2,0,window=self.filter_frame,anchor='nw')
        self.tree=ttk.Treeview(holder,columns=[k for k,_,_ in columns],show='',selectmode='browse',style=readable_table(parent,pending=True))
        if hierarchy:
            self.tree.configure(show='tree',displaycolumns=[k for k,_,_ in columns[1:]])
            self.tree.column('#0',width=columns[0][2],minwidth=columns[0][2],stretch=False)
        self.tree.tag_configure('dirty',background='#FFF0AD',foreground='#533F00')
        self.tree.tag_configure('selected_clean',background='#E7F5F6',foreground='#006B7D')
        for key,title,width in columns:
            self.tree.heading(key,text=title,command=lambda k=key:self.sort(k))
            self.tree.column(key,width=width,minwidth=width,stretch=key=='name')
            cell=ttk.Frame(self.filter_frame);self.cells.append(cell)
            header=ttk.Label(cell,text=title,font=('Microsoft JhengHei UI',10),cursor='hand2',takefocus=True)
            header.pack(fill='x',padx=3,pady=(0,4));self.headers[key]=header
            header.bind('<Button-1>',lambda e,k=key:self.sort(k))
            header.bind('<Return>',lambda e,k=key:self.sort(k));header.bind('<space>',lambda e,k=key:self.sort(k))
            var=tk.StringVar(value=ALL);self.filters[key]=var
            combo=ttk.Combobox(cell,textvariable=var,values=[ALL,EMPTY,NONEMPTY],state='readonly' if key in ENUM_COLUMNS else 'normal',font=('Microsoft JhengHei UI',11))
            combo.pack(fill='x',padx=3,pady=(0,6));self.filter_widgets[key]=combo
            var.trace_add('write',self.refilter)
        self.tree.grid(row=1,column=0,sticky='nsew')
        self.vertical=ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview);self.vertical.grid(row=1,column=1,sticky='ns')
        self.horizontal=ttk.Scrollbar(holder,orient='horizontal',command=self.scroll);self.horizontal.grid(row=2,column=0,sticky='ew')
        self.tree.configure(yscrollcommand=self.vertical.set,xscrollcommand=self.scrolled)
        self.tree.bind('<<TreeviewSelect>>',lambda _:(self.paint_rows(),self.on_select(self.selected())))
        self.tree.bind('<Configure>',lambda _:self.tree.after_idle(self.align))
        self.tree.bind('<ButtonRelease-1>',lambda _:self.tree.after_idle(self.align),add=True)
        self.query.trace_add('write',self.refilter)
        self.align()

    def align(self):
        if not self.tree.winfo_exists():return
        height=max((h.winfo_reqheight()+self.filter_widgets[k].winfo_reqheight()+10 for k,h in self.headers.items()),default=60)
        self.canvas.configure(height=height)
        left=0
        for (key,_,_),cell in zip(self.columns,self.cells):
            width=self.tree.column('#0' if self.hierarchy and key==self.columns[0][0] else key,'width');cell.place(x=left,y=0,width=width,height=height);left+=width
        self.filter_frame.configure(width=left,height=height)
        self.canvas.configure(scrollregion=(0,0,left+4,height));self.canvas.xview_moveto(self.tree.xview()[0])

    def scroll(self,*args):
        self.tree.xview(*args)
        self.canvas.xview_moveto(self.tree.xview()[0])

    def scrolled(self,first,last):
        self.horizontal.set(first,last);self.canvas.xview_moveto(first)

    def selected(self):
        selection=self.tree.selection()
        return self.rows[int(selection[0])] if selection else None

    def clear_filters(self):
        self.suspend=True
        self.query.set('')
        for var in self.filters.values():var.set(ALL)
        self.suspend=False;self.refilter()

    def set_rows(self,rows):
        self.rows=rows
        for key in ENUM_COLUMNS & self.filters.keys():
            self.filter_widgets[key].configure(values=[ALL,*sorted({str(r.get(key) or '') for r in rows}-{''},key=natural_key),EMPTY,NONEMPTY])
        self.refilter()

    def sort(self,column):
        self.descending=not self.descending if self.column==column else False
        self.column=column
        for key,title,_ in self.columns:
            text=title+(' ▼' if self.descending else ' ▲') if key==column else title
            self.tree.heading(key,text=text);self.headers[key].configure(text=text)
        self.refilter()

    def refilter(self,*_):
        if self.suspend:return
        before=self.tree.selection();opened={iid for iid in self.tree.get_children() if self.tree.item(iid,'open')}
        self.tree.delete(*self.tree.get_children())
        selected=select_rows(self.rows,self.query.get(),{k:v.get() for k,v in self.filters.items()},self.column,self.descending)
        if self.hierarchy:
            matched={i for i,_ in selected};wanted=set(matched)
            for index in matched:
                parent=self.rows[index].get('_parent')
                if parent is not None:wanted.add(parent)
            wanted.update(i for i,r in enumerate(self.rows) if r.get('_parent') in matched)
            ordered=select_rows(self.rows,column=self.column,descending=self.descending)
            children={}
            for i,r in ordered:
                if i in wanted and '_parent' in r:children.setdefault(r['_parent'],[]).append((i,r))
            selected=[]
            for index,row in ordered:
                if index not in wanted or '_parent' in row:continue
                selected.append((index,row))
                selected.extend(children.get(index,[]))
        filtered=bool(self.query.get().strip()) or any(v.get()!=ALL for v in self.filters.values())
        for index,row in selected:
            parent=str(row['_parent']) if self.hierarchy and '_parent' in row else ''
            self.tree.insert(parent,'end',iid=str(index),text=row.get(self.columns[0][0],''),
                open=str(index) in opened or (self.hierarchy and filtered),values=[row.get(k,'') for k,_,_ in self.columns])
        if before and self.tree.exists(before[0]):self.tree.selection_set(before[0])
        self.paint_rows()
        self.on_select(self.selected())
        total=sum(bool(v.get().strip() and v.get()!=ALL) for v in self.filters.values())
        self.count.set(f'顯示 {len(selected)}／{len(self.rows)} 筆'+(f' · 已套用 {total} 個欄位篩選' if total else '')+(' · 沒有符合的資料，請調整或清除篩選。' if not selected else ''))

    def paint_rows(self):
        selected=set(self.tree.selection())
        for index in range(len(self.rows)):
            iid=str(index)
            if not self.tree.exists(iid):continue
            row=self.rows[int(iid)]
            self.tree.item(iid,tags=('dirty',) if row.get('_dirty') else ('selected_clean',) if iid in selected else ())

    def update_rows(self,key,values,dirty):
        # Do not refilter while typing: retain focus and show the pending values.
        for index,row in enumerate(self.rows):
            if row.get('key')!=key:continue
            row.update(values);row['_dirty']=dirty
            if self.tree.exists(str(index)):
                self.tree.item(str(index),values=[row.get(k,'') for k,_,_ in self.columns])
        self.paint_rows()
