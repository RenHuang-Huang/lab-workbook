"""PDF column target sizes. Kept separate from fixed column geometry."""
import math

FIELDS=(
    ('clinic','診所',8),('workno','工作號',14),('visit_date','就醫日期（日／月）',11),
    ('name','姓名',14),('sex','性別',14),('chart_number','病歷號／保險',14),
    ('adult_health','@ 成健',11),('bio','生化／糞便',11),('cbc','CBC／尿液',11),
    ('sendout','外送／備註',11),('e411','e411',12),('other','其他（HbA1c、mab）',12),
)
DEFAULTS={key:float(size) for key,_,size in FIELDS}
MIN_SIZE,MAX_SIZE=6,24


def sizes(settings):
    saved=settings.get('font_sizes',{})
    if not isinstance(saved,dict):raise ValueError('列印字體設定格式不正確。')
    result=dict(DEFAULTS)
    for key,label,_ in FIELDS:
        if key not in saved:continue
        try:
            value=float(saved[key])
            if isinstance(saved[key],bool) or not math.isfinite(value) or not MIN_SIZE<=value<=MAX_SIZE:raise ValueError
        except (TypeError,ValueError):
            raise ValueError(f'「{label}」字級請輸入 {MIN_SIZE}～{MAX_SIZE} pt 的數字。') from None
        result[key]=value
    return result


class FontSettings:
    def __init__(self,parent,settings,on_save):
        import tkinter as tk
        from tkinter import ttk
        self.window=tk.Toplevel(parent);self.window.title('列印字體設定')
        self.window.geometry('760x570');self.window.minsize(720,540);self.window.transient(parent)
        self.on_save=on_save;self.variables={};self.inputs={}
        body=ttk.Frame(self.window,padding=20);body.pack(fill='both',expand=True)
        ttk.Label(body,text='各欄字體大小',font=('Microsoft JhengHei UI',17,'bold')).pack(anchor='w')
        ttk.Label(body,text='單位 pt；數字越大，字越高。欄寬固定，列高依分頁設定調整。').pack(anchor='w',pady=(8,4))
        ttk.Label(body,text='工作號等欄位會先縮緊字寬；長內容、多筆日期及密集項目會自動換行或縮小。',
                  wraplength=670).pack(anchor='w',pady=(0,14))
        fields=ttk.Frame(body);fields.pack(fill='x')
        values=sizes(settings)
        for index,(key,label,_) in enumerate(FIELDS):
            row,col=index%6,(index//6)*3
            ttk.Label(fields,text=label).grid(row=row,column=col,sticky='w',padx=(0,10),pady=9)
            var=tk.StringVar(value=f'{values[key]:g}');self.variables[key]=var
            box=ttk.Spinbox(fields,textvariable=var,from_=MIN_SIZE,to=MAX_SIZE,increment=.5,width=6)
            box.grid(row=row,column=col+1,sticky='w',pady=9);self.inputs[key]=box
            ttk.Label(fields,text='pt').grid(row=row,column=col+2,sticky='w',padx=(5,24))
        self.status=tk.StringVar()
        ttk.Label(body,textvariable=self.status,foreground='#b02631',wraplength=670).pack(anchor='w',pady=(10,0))
        buttons=ttk.Frame(body);buttons.pack(side='bottom',fill='x',pady=(12,0))
        ttk.Button(buttons,text='恢復預設字級',command=self.reset).pack(side='left')
        ttk.Button(buttons,text='取消',command=self.window.destroy).pack(side='right')
        self.save_button=ttk.Button(buttons,text='儲存字體設定',command=self.save)
        self.save_button.pack(side='right',padx=10)

    def reset(self):
        for key,value in DEFAULTS.items():self.variables[key].set(f'{value:g}')
        self.status.set('已填入預設值；按「儲存字體設定」後生效。')

    def save(self):
        try:
            values=sizes({'font_sizes':{k:v.get() for k,v in self.variables.items()}})
            self.on_save(values)
        except ValueError as error:
            self.status.set(str(error));return False
        except OSError:
            self.status.set('無法儲存字體設定，請確認程式資料夾可寫入。');return False
        self.window.destroy();return True
