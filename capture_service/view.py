"""按本项目约定展示已接收资料、已确认范围与明确缺口。"""
from .ledger import entities
from .domain import assess

def overview(c,collection,as_of=None):
    rows=entities(c,collection,as_of)
    result=assess(rows,as_of)
    result['collection']=collection
    result['records']=[{'type':r['type'],'id':r['id'],'version':r['version'],
                        'source_sha256':r['source'],'recorded_at':r.get('recorded_at'),
                        'source_url':r.get('source_url')} for r in rows]
    return result
