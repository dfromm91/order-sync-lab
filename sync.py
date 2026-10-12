"""Small order-to-ERP integration lab. Synthetic data; no NetSuite access."""
import hashlib
import json
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCHEMA = '''
CREATE TABLE IF NOT EXISTS outbox (
 id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0, error TEXT);
'''

def connect(path='orders.db'):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db

def normalize(order):
    """Validate source records and convert money to integer cents, never floats."""
    if not isinstance(order, dict):
        raise ValueError('Order must be an object')
    for name in ('id', 'customer', 'sku'):
        if not isinstance(order.get(name), str) or not order[name].strip():
            raise ValueError(f'{name} must be a nonempty string')
    qty = order.get('quantity')
    if type(qty) is not int or qty <= 0:
        raise ValueError('quantity must be a positive integer')
    if not isinstance(order.get('unit_price'), str):
        raise ValueError('unit_price must be a decimal string')
    try:
        value = Decimal(order['unit_price'])
        if not value.is_finite() or value < 0 or value * 100 != (value * 100).to_integral_value():
            raise ValueError('unit_price must be nonnegative with whole cents')
        cents = int(value * 100)
    except InvalidOperation as exc:
        raise ValueError('Invalid unit_price') from exc
    if cents * qty > 1_000_000_000:
        raise ValueError('Order exceeds demo limit')
    return {'external_id':order['id'].strip(), 'customer_ref':order['customer'].strip(),
            'item_ref':order['sku'].strip(), 'quantity':qty, 'unit_price_cents':cents,
            'total_cents':cents * qty}

def enqueue(db, source):
    """Stable external ID prevents duplicate submissions; changed payload is a conflict."""
    payload = normalize(source)
    encoded = json.dumps(payload, sort_keys=True)
    existing = db.execute('SELECT payload FROM outbox WHERE id=?', (payload['external_id'],)).fetchone()
    if existing:
        if existing[0] != encoded:
            raise ValueError('Conflicting payload for existing order ID')
        return False
    with db:
        db.execute('INSERT INTO outbox(id,payload) VALUES (?,?)', (payload['external_id'], encoded))
    return True

class RestERP:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
    def send(self, payload):
        key = hashlib.sha256(payload['external_id'].encode()).hexdigest()
        request = Request(self.base_url + '/orders', data=json.dumps(payload).encode(),
            headers={'Content-Type':'application/json','Idempotency-Key':key}, method='POST')
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    def orders(self):
        with urlopen(self.base_url + '/orders', timeout=5) as response:
            return json.load(response)

def flush(db, erp, limit=3, sleep=time.sleep):
    """Retry transient failures, quarantine permanent failures. Sequential demo worker."""
    for order_id, encoded, attempts in db.execute(
            "SELECT id,payload,attempts FROM outbox WHERE state='pending'").fetchall():
        while attempts < limit:
            attempts += 1
            try:
                erp.send(json.loads(encoded))
            except (HTTPError, URLError, TimeoutError) as exc:
                transient = not isinstance(exc, HTTPError) or exc.code in (429,500,502,503,504)
                state = 'pending' if transient else 'failed'
                with db:
                    db.execute('UPDATE outbox SET attempts=?,state=?,error=? WHERE id=?',
                        (attempts,state,str(exc),order_id))
                if not transient:
                    break
                if attempts < limit:
                    sleep(0.05 * 2 ** (attempts - 1))
            else:
                with db:
                    db.execute("UPDATE outbox SET attempts=?,state='sent',error=NULL WHERE id=?", (attempts,order_id))
                break
        else:
            with db:
                db.execute("UPDATE outbox SET state='failed',error='Retry budget exhausted' WHERE id=?", (order_id,))

def reconcile(db, erp):
    """Compare accepted totals to remote state; report missing and altered records."""
    remote = {x['external_id']:x for x in erp.orders()}
    issues = []
    for order_id, encoded in db.execute("SELECT id,payload FROM outbox WHERE state='sent'"):
        expected = json.loads(encoded)
        if order_id not in remote:
            issues.append({'id':order_id,'issue':'missing'})
        elif expected != remote[order_id]:
            issues.append({'id':order_id,'issue':'mismatch'})
    return issues
