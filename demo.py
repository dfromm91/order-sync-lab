"""Run a real HTTP integration against an in-memory mock ERP."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from sync import connect, enqueue, flush, reconcile, RestERP

class MockERP(BaseHTTPRequestHandler):
    records = {}
    failures = 0
    def log_message(self, *args):
        pass
    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if self.path != '/orders':
            return self.reply(404, {'error':'Not found'})
        if type(self).failures:
            type(self).failures -= 1
            return self.reply(503, {'error':'Synthetic temporary outage'})
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        key = self.headers.get('Idempotency-Key')
        if not key:
            return self.reply(400, {'error':'Missing key'})
        prior = self.records.get(key)
        if prior and prior != data:
            return self.reply(409, {'error':'Conflicting payload'})
        self.records[key] = data
        self.reply(200 if prior else 201, data)
    def do_GET(self):
        if self.path != '/orders':
            return self.reply(404, {'error':'Not found'})
        self.reply(200, list(self.records.values()))

def start_mock(failures=0):
    MockERP.records = {}
    MockERP.failures = failures
    server = ThreadingHTTPServer(('127.0.0.1',0),MockERP)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server, RestERP(f'http://127.0.0.1:{server.server_port}')

if __name__ == '__main__':
    server, erp = start_mock(failures=1)
    db = connect(':memory:')
    try:
        source = {'id':'DEMO-001','customer':'SYNTHETIC-CUSTOMER','sku':'SENSOR-A','quantity':3,'unit_price':'19.95'}
        enqueue(db,source)
        assert not enqueue(db,source)
        flush(db,erp)
        print(json.dumps({'outbox':db.execute('SELECT id,state,attempts FROM outbox').fetchall(),
                         'erp_orders':erp.orders(),'reconciliation':reconcile(db,erp)},indent=2))
        assert db.execute('SELECT state FROM outbox').fetchone()[0] == 'sent'
        assert reconcile(db,erp) == []
    finally:
        db.close()
        server.shutdown()
        server.server_close()
