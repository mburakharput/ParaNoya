"""Reserve SQLite's writer before checking financial invariants."""
from contextlib import contextmanager
from uuid import uuid4


@contextmanager
def write_transaction(db):
    nested = db.in_transaction
    savepoint = 'finance_' + uuid4().hex
    if nested:
        db.execute('SAVEPOINT ' + savepoint)
    else:
        db.execute('BEGIN IMMEDIATE')
    try:
        if nested:
            # SAVEPOINT alone does not reserve a writer. Even with zero matching
            # rows SQLite obtains the write lock before the financial SELECTs.
            db.execute('UPDATE profiles SET id=id WHERE 0')
        yield
        if nested:
            db.execute('RELEASE SAVEPOINT ' + savepoint)
        else:
            db.commit()
    except BaseException:
        if nested:
            db.execute('ROLLBACK TO SAVEPOINT ' + savepoint)
            db.execute('RELEASE SAVEPOINT ' + savepoint)
        else:
            db.rollback()
        raise
