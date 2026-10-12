import unittest
from urllib.error import HTTPError
from sync import connect, enqueue, normalize, flush, reconcile
from demo import start_mock

ORDER={'id':'A','customer':'Synthetic','sku':'ITEM','quantity':3,'unit_price':'0.10'}
class Tests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:')
    def tearDown(self):
        self.db.close()
    def test_money_exact(self):
        self.assertEqual(normalize(ORDER)['total_cents'],30)
    def test_invalid_money(self):
        for value in ('NaN','Infinity','-1','0.001','bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(dict(ORDER,unit_price=value))
    def test_invalid_quantities(self):
        for value in (True,0,-1,1.5,'3'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                normalize(dict(ORDER,quantity=value))
    def test_duplicate_and_conflict(self):
        self.assertTrue(enqueue(self.db,ORDER))
        self.assertFalse(enqueue(self.db,ORDER))
        with self.assertRaises(ValueError):
            enqueue(self.db,dict(ORDER,quantity=4))
    def test_http_retry_and_idempotency(self):
        server,erp=start_mock(failures=1)
        try:
            enqueue(self.db,ORDER); flush(self.db,erp,sleep=lambda _:None)
            self.assertEqual(self.db.execute('SELECT state,attempts FROM outbox').fetchone(),('sent',2))
            erp.send(normalize(ORDER))
            self.assertEqual(len(erp.orders()),1)
            self.assertEqual(reconcile(self.db,erp),[])
        finally:
            server.shutdown(); server.server_close()
    def test_permanent_failure(self):
        class Reject:
            def send(self,payload):
                raise HTTPError('mock',400,'bad data',{},None)
        enqueue(self.db,ORDER); flush(self.db,Reject(),sleep=lambda _:None)
        self.assertEqual(self.db.execute('SELECT state,attempts FROM outbox').fetchone(),('failed',1))
    def test_retry_exhaustion(self):
        class Down:
            def send(self,payload):
                raise HTTPError('mock',503,'outage',{},None)
        enqueue(self.db,ORDER); flush(self.db,Down(),sleep=lambda _:None)
        self.assertEqual(self.db.execute('SELECT state,attempts FROM outbox').fetchone(),('failed',3))
    def test_reconciliation(self):
        enqueue(self.db,ORDER)
        self.db.execute("UPDATE outbox SET state='sent'")
        class Missing:
            def orders(self): return []
        class Changed:
            def orders(self): return [dict(normalize(ORDER),total_cents=99)]
        self.assertEqual(reconcile(self.db,Missing())[0]['issue'],'missing')
        self.assertEqual(reconcile(self.db,Changed())[0]['issue'],'mismatch')
if __name__=='__main__': unittest.main()
