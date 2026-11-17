"""将已接收原文和来源化实体写入同一事务;版本与首次接收时间只增不减。

重复抓取与站点短暂回退重发的旧版原文都是幂等空操作:实体按
(类型,标识,版次) 保存首次接收时间 recorded_at,已接收的新版次不会被抹掉。
"""
import hashlib
import json
import sqlite3
from .domain import decode

SCHEMA="""
CREATE TABLE IF NOT EXISTS receipts(
  collection TEXT NOT NULL, body_sha256 TEXT NOT NULL, source_url TEXT NOT NULL,
  status INTEGER NOT NULL, observed_at TEXT, raw BLOB NOT NULL,
  PRIMARY KEY(collection,body_sha256));
CREATE TABLE IF NOT EXISTS entities(
  collection TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  version TEXT NOT NULL, receipt_sha256 TEXT NOT NULL, recorded_at TEXT, payload_json TEXT NOT NULL,
  PRIMARY KEY(collection,entity_type,entity_id,version),
  FOREIGN KEY(collection,receipt_sha256) REFERENCES receipts(collection,body_sha256));
"""

def connect(path):
    c=sqlite3.connect(path)
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript(SCHEMA)
    return c

def receive(c, collection, raw, receipt):
    if receipt['status']!=200:raise ValueError('来源响应非成功正文')
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=receipt['body_sha256']:raise ValueError('响应收据与原文不一致')
    observed=receipt.get('observed_at')
    rows=decode(raw,receipt)
    with c:
        c.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?,?)',
                  (collection,digest,receipt['url'],receipt['status'],observed,raw))
        for row in rows:
            payload=json.dumps(row['payload'],ensure_ascii=False,sort_keys=True)
            key=(collection,row['type'],row['id'],row['version'])
            prior=c.execute('SELECT receipt_sha256,payload_json FROM entities WHERE collection=? AND entity_type=? AND entity_id=? AND version=?',key).fetchone()
            if prior and prior!=(digest,payload):raise ValueError('同一实体版本的原文发生冲突')
            c.execute('INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?,?)',(*key,digest,observed,payload))
    return digest

def entities(c,collection,as_of=None):
    """按观察时间回放:只取 recorded_at 不晚于 as_of 的版本;无时间戳的旧资料始终可见。"""
    sql=('SELECT e.entity_type,e.entity_id,e.version,e.receipt_sha256,e.recorded_at,e.payload_json,r.source_url '
         'FROM entities e JOIN receipts r ON r.collection=e.collection AND r.body_sha256=e.receipt_sha256 '
         'WHERE e.collection=?')
    params=[collection]
    if as_of is not None:
        sql+=' AND (e.recorded_at IS NULL OR e.recorded_at<=?)'
        params.append(as_of)
    sql+=' ORDER BY e.entity_type,e.entity_id,e.version'
    return [dict(type=row[0],id=row[1],version=row[2],source=row[3],recorded_at=row[4],
                 payload=json.loads(row[5]),source_url=row[6])
            for row in c.execute(sql,params)]
