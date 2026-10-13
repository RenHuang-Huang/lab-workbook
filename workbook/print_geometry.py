"""Stable horizontal slots and shared, centered vertical grids."""
from . import subregions as sr

BASE_COLUMNS={'bio':6,'cbc':1,'sendout':1,'e411':1,'other':1}


def column_counts(rows,layout):
    """Use one slot width for the export, independent of a row's missing groups.

    Explicit extra subregions reserve more columns. Dense automatic overflow only
    compresses that row after force confirmation, not every ordinary CBC row.
    """
    result=dict(BASE_COLUMNS)
    for row in rows:
        if row is None:continue
        for zone,key in sr.ZONE_KEYS.items():
            explicit={i.get('placement',{}).get('subregion') for i in row['zones'][key]}-{None,''}
            if not explicit:continue
            stop=max(sr.LETTERS.index(letter) for letter in explicit)+1
            count=sum(letter in explicit or not sr.options(layout,zone,letter)['compact_subregions'] for letter in sr.LETTERS[:stop])
            result[key]=max(result[key],count)
    return result


def lane_center(position,count,height):
    if count==2:return height/2+(position-1.5)*height/3
    return (position-.5)*height/count
