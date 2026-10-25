import tempfile
from pathlib import Path
from datetime import date
from finance_core import migrate,open_db,add_account,accounts_with_balances,summary
from v04_core import month_add
from kmh_core import migrate_kmh,closing_due,set_overdraft,overdraft,use_overdraft,add_installment_loan,monthly_calendar,pay_installment

def test_dates():
    assert month_add(date(2026, 11, 15), 1) == date(2026, 12, 15)
    assert month_add(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert closing_due('2026-11-05').isoformat()=='2026-11-15'
    assert closing_due('2026-11-25').isoformat()=='2026-12-05'
    assert closing_due('2027-02-28').isoformat()=='2027-03-10'

def test_kmh():
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'db.sqlite';migrate(p)
        with open_db(p) as db:
            migrate_kmh(db)
            add_account(db,1,'Banka','bank',100000)
            add_account(db,1,'Nakit','cash',300000)
            a=accounts_with_balances(db,1)
            od=set_overdraft(db,1,a[0][0],200000)
            use_overdraft(db,1,od,50000,'draw')
            assert overdraft(db,1)[0][-1]==50000
            assert accounts_with_balances(db,1)[0][-1]==150000
            use_overdraft(db,1,od,20000,'repay')
            assert overdraft(db,1)[0][-1]==30000
            loan=add_installment_loan(db,1,od,100000,[('2026-11-15',50000,1000,200,300),('2026-12-15',50000,1000,200,300)])
            rows=monthly_calendar(db,1)
            assert len(rows)==2 and rows[0][3]==51500
            assert summary(db,1)[0:2]==(0,0)
            bank_bal=accounts_with_balances(db,1)[0][-1]
            assert bank_bal==230000
            pay_installment(db,1,rows[0][0],a[1][0],51500)
            assert monthly_calendar(db,1)[0][2]=='2026-12-15'
            assert accounts_with_balances(db,1)[1][-1]==248500
            try:pay_installment(db,1,rows[0][0],a[1][0],100)
            except ValueError: pass
            else:raise AssertionError('overpayment accepted')

if __name__=='__main__':
    test_dates();test_kmh();print('KMH tests passed')
