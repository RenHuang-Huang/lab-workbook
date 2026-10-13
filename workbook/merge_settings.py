"""Configurable work-number exclusions; no patient identifiers or database reads."""
import re

DEFAULT_EXCLUSIONS=('9','10','69','70','129','130')


def work_number(value):
    text=str(value).strip()
    return str(int(text)) if text.isascii() and text.isdecimal() else text


def exclusion_values(values):
    if not isinstance(values,list):raise ValueError('不併單工作號必須是清單。')
    result=[]
    for value in values:
        if type(value) not in (str,int) or not str(value).strip().isascii() or not str(value).strip().isdecimal():
            raise ValueError('不併單工作號請填入非負整數，並用逗號分隔。')
        number=work_number(value)
        if number not in result:result.append(number)
    return result


def parse_exclusions(text):
    return exclusion_values([v.strip() for v in re.split(r'[,，、;；|\s]+',text) if v.strip()])


def exclusions(settings):
    enabled=settings.get('merge_exclusions_enabled',True)
    if type(enabled) is not bool:raise ValueError('指定工作號不併單必須為勾選值。')
    values=exclusion_values(settings.get('merge_excluded_worknos',list(DEFAULT_EXCLUSIONS)))
    return set(values) if enabled else set()
