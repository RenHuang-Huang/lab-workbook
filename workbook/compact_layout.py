"""Lossless emergency packing inside the existing row and zone boundaries."""
def pack_segments(tokens,width,height,measure,max_lanes=5,start_size=10.5):
    size=start_size
    for attempt in range(180):
        result_space=min(3.5,width*.22) if size>=6 else min(2,width*.15)*size/6
        padding=min(1.5,size/4)
        pieces=[]
        for segments,has_result in tokens:
            chars=[(ch,color) for value,color in segments for ch in str(value)]
            room=width-padding-(result_space if has_result else 0)
            groups=[[]];used=0
            for ch,color in chars:
                cw=measure(ch,size)
                # Prefer intact test names at a slightly smaller size. Split only
                # unusually long names after exhausting normally readable sizes.
                if size<6 and used+cw>room and groups[-1]:groups.append([]);used=0
                groups[-1].append((ch,color));used+=cw
            for index,group in enumerate(groups):
                reserve=result_space if has_result and index==len(groups)-1 else 0
                runs=[]
                for ch,color in group:
                    if runs and runs[-1][1]==color:runs[-1]=(runs[-1][0]+ch,color)
                    else:runs.append((ch,color))
                pieces.append({'runs':runs,'width':sum(measure(ch,size) for ch,_ in group)+reserve+padding,'result':reserve,'padding':padding})
        lanes=[[]];used=0
        for piece in pieces:
            if used+piece['width']>width and lanes[-1]:lanes.append([]);used=0
            lanes[-1].append(piece);used+=piece['width']
        if (len(lanes)<=max_lanes and size/72*25.4*1.22<=height/len(lanes)-.3
                and all(p['width']<=width for p in pieces)):
            return size,lanes
        size*=.9
    raise ValueError('強制排版無法完成，請檢查項目名稱或欄位設定')
