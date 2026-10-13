"""Stable horizontal slots and shared, centered vertical grids."""
from . import subregions as sr
from .errors import LayoutCapacityError

BASE_COLUMNS={'bio':6,'cbc':1,'sendout':1,'e411':1,'other':1}


def column_counts(rows,layout):
    """Use one slot width for the export, independent of a row's missing groups.

    Include three-row overflow columns so a fourth item starts the next column.
    """
    result=dict(BASE_COLUMNS)
    for row in rows:
        if row is None:continue
        for zone,key in sr.ZONE_KEYS.items():
            items=list(row['zones'][key])
            if key=='sendout' and row.get('notes'):items.append({'label':'備註：'+row['notes']})
            try:
                groups=sr.arrange(items,zone,layout)
                result[key]=max(result[key],max((g['column']+1 for g in groups),default=0))
            except LayoutCapacityError:
                # Force-only overflow must not resize every ordinary row.
                pass
            explicit={i.get('placement',{}).get('subregion') for i in row['zones'][key]}-{None,''}
            if not explicit:continue
            stop=max(sr.LETTERS.index(letter) for letter in explicit)+1
            count=sum(letter in explicit or not sr.options(layout,zone,letter)['compact_subregions'] for letter in sr.LETTERS[:stop])
            result[key]=max(result[key],count)
    return result


def lane_center(position,count,height):
    if count==2:return height/2+(position-1.5)*height/3
    return (position-.5)*height/count
