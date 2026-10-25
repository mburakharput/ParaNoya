import unittest
from datetime import date
from payment_calendar import summarize_calendar, filter_calendar

class PaymentCalendarTests(unittest.TestCase):
    def setUp(self):
        self.today=date(2026,10,25)
        self.rows=[(1,'A','2026-09-15',2000,'eski'),(2,'A','2026-10-15',3000,'geç'),(3,'B','2026-10-28',5000,'yakın'),(4,'B','2026-11-15',7000,'sonraki')]
    def test_summary(self):
        self.assertEqual(summarize_calendar(self.rows,self.today),{'total':17000,'overdue':5000,'this_month':8000})
    def test_filter(self):
        self.assertEqual([r[0] for r in filter_calendar(self.rows,'overdue',self.today)],[1,2])
        self.assertEqual([r[0] for r in filter_calendar(self.rows,'this_month',self.today)],[2,3])
        self.assertEqual([r[0] for r in filter_calendar(self.rows,'future',self.today)],[3,4])
    def test_bad_filter(self):
        with self.assertRaises(ValueError):filter_calendar(self.rows,'unknown',self.today)
    def test_invalid_negative_amount(self):
        with self.assertRaises(ValueError):summarize_calendar([(1,'A','2026-10-25',-1,'')],self.today)

if __name__=='__main__':unittest.main()
