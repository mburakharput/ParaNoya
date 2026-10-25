"""KMH aylık ödeme takviminin saf özetleme ve filtreleme kuralları."""
from datetime import date


def summarize_calendar(rows, today=None):
    today = today or date.today()
    ym = today.strftime('%Y-%m')
    amounts = {'total': 0, 'overdue': 0, 'this_month': 0}
    for _, _, due, amount, _ in rows:
        if amount < 0: raise ValueError('Ödenmemiş tutar negatif olamaz.')
        d = date.fromisoformat(due)
        amounts['total'] += amount
        if d < today: amounts['overdue'] += amount
        if due[:7] == ym: amounts['this_month'] += amount
    return amounts


def filter_calendar(rows, mode='all', today=None):
    today = today or date.today()
    if mode not in ('all', 'this_month', 'overdue', 'future'):
        raise ValueError('Geçersiz takvim filtresi')
    result=[]
    for row in rows:
        due=date.fromisoformat(row[2])
        if mode=='all' or (mode=='this_month' and (due.year,due.month)==(today.year,today.month)) or (mode=='overdue' and due<today) or (mode=='future' and due>=today):
            result.append(row)
    return result
