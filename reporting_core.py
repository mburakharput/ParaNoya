"""Read-only dashboard aggregates; amounts are integer kuruş.

Purchases count as expenses on purchase dates. Card debt payments only move
cash and reduce liabilities, so they never enter income/expense trend totals.
"""
from datetime import date


def _month_add(origin, offset):
    total = origin.year * 12 + origin.month - 1 + offset
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def monthly_trend(db, profile_id, *, today=None, months=6):
    """Return exactly the last N calendar months, including zero-activity months."""
    if type(months) is not int or not 1 <= months <= 120:
        raise ValueError("Rapor ay sayısı 1-120 arasında tam sayı olmalı")
    today = today or date.today()
    start = _month_add(today.replace(day=1), 1 - months)
    stop = _month_add(today.replace(day=1), 1)
    first, last = start.isoformat(), stop.isoformat()
    rows = db.execute("""
        SELECT month, kind, SUM(amount_cents) FROM (
          SELECT substr(recorded_at,1,7) AS month, kind, amount_cents
          FROM transactions
          WHERE profile_id=? AND recorded_at>=? AND recorded_at<?
          UNION ALL
          SELECT substr(p.purchase_date,1,7) AS month, 'expense' AS kind,
                 p.total_cents AS amount_cents
          FROM card_purchases p
          JOIN credit_cards c ON c.id=p.card_id
          WHERE c.profile_id=? AND p.purchase_date>=? AND p.purchase_date<?
        ) GROUP BY month,kind
    """, (profile_id, first, last, profile_id, first, last)).fetchall()
    values = {}
    for month, kind, amount in rows:
        bucket = values.setdefault(month, [0, 0])
        bucket[0 if kind == 'income' else 1] += amount
    result = []
    for index in range(months):
        month = _month_add(start, index).isoformat()[:7]
        income, expense = values.get(month, (0, 0))
        result.append((month, income, expense))
    return result


def category_expenses(db, profile_id):
    """Combine cash expenses with card purchases; never double-count repayments."""
    return db.execute("""
        SELECT category,SUM(amount_cents) FROM (
          SELECT category,amount_cents
          FROM transactions WHERE profile_id=? AND kind='expense'
          UNION ALL
          SELECT p.category,p.total_cents
          FROM card_purchases p JOIN credit_cards c ON c.id=p.card_id
          WHERE c.profile_id=?
        ) GROUP BY category ORDER BY SUM(amount_cents) DESC,category
    """, (profile_id, profile_id)).fetchall()
