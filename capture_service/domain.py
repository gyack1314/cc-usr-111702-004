"""解释企业公告、附件清单、注册信息、批号附件、流通清单、更正与媒体报道。

每类资料都保留各自来源与版次;更正只作用于其明确覆盖的目标版次与字段;
媒体报道只允许组级数量,不得提供批号级范围,防止借组级数字捏造批号。
"""
import json
import re
from urllib.parse import urlsplit

RANGE_STATUSES=('confirmed','pending_confirmation','cleared')
ENTRY_KINDS=('ranges','distribution')

def _require(doc,*fields):
    missing=[f for f in fields if f not in doc]
    if missing:raise ValueError('企业召回资料缺少字段:'+','.join(missing))

def _check_cells(cells):
    for cell in cells:
        _require(cell,'batch','region','status')
        if cell['status'] not in RANGE_STATUSES:
            raise ValueError('批号单元状态非法:'+str(cell['status']))

def decode(raw,receipt):
    doc=json.loads(raw.decode('utf-8'))
    if 'attachments' in doc and 'entries' in doc:
        _require(doc,'attachments','revision','notice','entries')
        entries=[]
        for e in doc['entries']:
            _require(e,'id','revision')
            kind=e.get('kind','ranges')
            if kind not in ENTRY_KINDS:raise ValueError('附件清单条目类型非法:'+str(kind))
            entries.append({'id':e['id'],'revision':e['revision'],'kind':kind})
        return [{'type':'attachments','id':doc['attachments'],'version':doc['revision'],
                 'payload':{'notice':doc['notice'],'entries':entries}}]
    if 'notice' in doc:
        _require(doc,'notice','revision','effective','product','attachments')
        payload={'effective':doc['effective'],'product':doc['product'],'attachments':doc['attachments']}
        if 'registration' in doc:payload['registration']=doc['registration']
        return [{'type':'notice','id':doc['notice'],'version':doc['revision'],'payload':payload}]
    if 'annex' in doc:
        _require(doc,'annex','revision','ranges')
        _check_cells(doc['ranges'])
        return [{'type':'annex','id':doc['annex'],'version':doc['revision'],
                 'payload':{'ranges':[dict(r) for r in doc['ranges']]}}]
    if 'registration' in doc:
        _require(doc,'registration','revision','product')
        payload={'product':doc['product']}
        for k in ('approval_no','holder','status'):
            if k in doc:payload[k]=doc[k]
        return [{'type':'registration','id':doc['registration'],'version':doc['revision'],'payload':payload}]
    if 'distribution' in doc:
        _require(doc,'distribution','revision','entries')
        _check_cells(doc['entries'])
        return [{'type':'distribution','id':doc['distribution'],'version':doc['revision'],
                 'payload':{'entries':[dict(e) for e in doc['entries']]}}]
    if 'correction' in doc:
        _require(doc,'correction','revision','effective','target')
        target=doc['target']
        if 'annex' in target:
            _require(target,'annex','version')
            _require(doc,'ranges')
            _check_cells(doc['ranges'])
            payload={'effective':doc['effective'],
                     'target':{'annex':target['annex'],'version':target['version']},
                     'ranges':[dict(r) for r in doc['ranges']]}
        elif 'notice' in target:
            _require(target,'notice','version')
            _require(doc,'set')
            if not isinstance(doc['set'],dict) or not doc['set']:
                raise ValueError('更正未明确覆盖字段')
            payload={'effective':doc['effective'],
                     'target':{'notice':target['notice'],'version':target['version']},
                     'set':dict(doc['set'])}
        else:
            raise ValueError('更正目标非法')
        return [{'type':'correction','id':doc['correction'],'version':doc['revision'],'payload':payload}]
    if 'media' in doc:
        if 'ranges' in doc:raise ValueError('媒体报道不得提供批号级范围')
        _require(doc,'media','group_quantities')
        payload={'group_quantities':doc['group_quantities']}
        for k in ('publisher','product','published'):
            if k in doc:payload[k]=doc[k]
        return [{'type':'media','id':doc['media'],'version':doc.get('revision','v1'),'payload':payload}]
    raise ValueError('企业召回资料非法')

def _version_key(version):
    return tuple((0,int(p)) if p.isdigit() else (1,p) for p in re.split(r'(\d+)',str(version)))

def _origin(url):
    if not url:return None
    parsed=urlsplit(url)
    if parsed.scheme and parsed.netloc:return parsed.scheme+'://'+parsed.netloc.lower()
    return None

def assess(rows,as_of=None):
    """按生效版次解释已接收资料;rows 须已按观察时间过滤。"""
    rows=[dict(r,origin=_origin(r.get('source_url'))) for r in rows]
    by_type={}
    for r in rows:
        by_type.setdefault(r['type'],{}).setdefault(r['id'],[]).append(r)
    def latest(t,i):
        cand=by_type.get(t,{}).get(i)
        return max(cand,key=lambda r:_version_key(r['version'])) if cand else None
    def exact(t,i,v):
        for r in by_type.get(t,{}).get(i,[]):
            if r['version']==v:return r
        return None
    def newer_versions(t,i,v):
        seen=[r['version'] for r in by_type.get(t,{}).get(i,[])
              if _version_key(r['version'])>_version_key(v)]
        return sorted(seen,key=_version_key)
    corrections=sorted((latest('correction',i) for i in by_type.get('correction',{})),
                       key=lambda c:(c['payload']['effective'],c['id']))
    applied=set()
    def annex_cells(ann,mark):
        """附件版次的有效单元:先取附件原文,再应用明确指向该版次的更正。"""
        cells={}
        for r in ann['payload']['ranges']:
            cells[(r['batch'],r['region'])]={'batch':r['batch'],'region':r['region'],'status':r['status'],
                'entity':'annex','id':ann['id'],'version':ann['version'],'source':ann['source'],
                'origin':ann['origin'],'recorded_at':ann.get('recorded_at'),'via':None}
        used=[]
        for c in corrections:
            t=c['payload']['target']
            if t.get('annex')==ann['id'] and t.get('version')==ann['version']:
                for r in c['payload']['ranges']:
                    cells[(r['batch'],r['region'])]={'batch':r['batch'],'region':r['region'],'status':r['status'],
                        'entity':'annex','id':ann['id'],'version':ann['version'],'source':c['source'],
                        'origin':c['origin'],'recorded_at':c.get('recorded_at'),'via':'correction:'+c['id']}
                used.append(c)
                if mark:applied.add((c['id'],c['version']))
        return sorted(cells.values(),key=lambda x:(x['batch'],x['region'])),used

    notices_out=[]
    conflicts=[]
    for nid in sorted(by_type.get('notice',{})):
        n=latest('notice',nid)
        payload=dict(n['payload'])
        notice_corrections=[]
        for c in corrections:
            t=c['payload']['target']
            if t.get('notice')==nid and t.get('version')==n['version']:
                payload.update(c['payload']['set'])
                notice_corrections.append(c)
                applied.add((c['id'],c['version']))
        entry={'id':nid,'version':n['version'],'effective':payload['effective'],
               'product':payload['product'],'source':n['source'],'origin':n['origin'],
               'recorded_at':n.get('recorded_at'),
               'confirmed_ranges':[],'pending_ranges':[],'cleared_ranges':[],
               'distribution':[],'corrections':[],'gaps':[],'notes':[]}
        for c in notice_corrections:
            entry['corrections'].append({'id':c['id'],'version':c['version'],'applied':True,
                                         'target':c['payload']['target'],'source':c['source']})
        reg_id=payload.get('registration')
        if reg_id:
            reg=latest('registration',reg_id)
            if not reg:
                entry['gaps'].append('产品注册信息未接收:'+reg_id)
            else:
                entry['registration']={'id':reg_id,'version':reg['version'],
                                       'product':reg['payload']['product'],
                                       'status':reg['payload'].get('status'),
                                       'source':reg['source'],'origin':reg['origin']}
                if reg['payload']['product']!=payload['product']:
                    conflicts.append({'kind':'product_mismatch','notice':nid,'statements':[
                        {'product':payload['product'],'entity':'notice','id':nid,'version':n['version'],
                         'source':n['source'],'origin':n['origin']},
                        {'product':reg['payload']['product'],'entity':'registration','id':reg_id,
                         'version':reg['version'],'source':reg['source'],'origin':reg['origin']}]})
        lst=latest('attachments',payload['attachments'])
        if not lst:
            entry['gaps'].append('附件清单未接收:'+payload['attachments'])
        else:
            entry['attachments']={'id':lst['id'],'version':lst['version'],
                                  'source':lst['source'],'origin':lst['origin']}
            for e in lst['payload']['entries']:
                if e['kind']=='ranges':
                    ann=exact('annex',e['id'],e['revision'])
                    if not ann:
                        other=by_type.get('annex',{}).get(e['id'])
                        if other:
                            seen=','.join(sorted((r['version'] for r in other),key=_version_key))
                            entry['notes'].append('已接收%s的其他版次:%s'%(e['id'],seen))
                        entry['gaps'].append('批号附件未接收:%s@%s'%(e['id'],e['revision']))
                        continue
                    newer=newer_versions('annex',e['id'],e['revision'])
                    if newer:
                        entry['notes'].append('已接收%s的更新版次:%s,附件清单仍指定%s'
                                              %(e['id'],','.join(newer),e['revision']))
                    cells,used=annex_cells(ann,mark=True)
                    for c in used:
                        entry['corrections'].append({'id':c['id'],'version':c['version'],'applied':True,
                                                     'target':c['payload']['target'],'source':c['source']})
                    for cell in cells:
                        cell=dict(cell,annex=ann['id'],annex_version=ann['version'])
                        if cell['status']=='confirmed':entry['confirmed_ranges'].append(cell)
                        elif cell['status']=='pending_confirmation':entry['pending_ranges'].append(cell)
                        else:entry['cleared_ranges'].append(cell)
                else:
                    dist=exact('distribution',e['id'],e['revision'])
                    if not dist:
                        entry['gaps'].append('流通清单未接收:%s@%s'%(e['id'],e['revision']))
                        continue
                    newer=newer_versions('distribution',e['id'],e['revision'])
                    if newer:
                        entry['notes'].append('已接收%s的更新版次:%s,附件清单仍指定%s'
                                              %(e['id'],','.join(newer),e['revision']))
                    for it in dist['payload']['entries']:
                        entry['distribution'].append({'batch':it['batch'],'region':it['region'],
                            'channel':it.get('channel'),'status':it['status'],
                            'id':dist['id'],'version':dist['version'],'source':dist['source'],
                            'origin':dist['origin'],'recorded_at':dist.get('recorded_at')})
        notices_out.append(entry)

    statements={}
    def add_stmt(batch,region,status,entity,id_,version,source,origin):
        statements.setdefault((batch,region),[]).append(
            {'status':status,'entity':entity,'id':id_,'version':version,'source':source,'origin':origin})
    for aid in sorted(by_type.get('annex',{})):
        ann=latest('annex',aid)
        cells,_=annex_cells(ann,mark=False)
        for cell in cells:
            add_stmt(cell['batch'],cell['region'],cell['status'],'annex',aid,ann['version'],
                     cell['source'],cell['origin'])
    for did in sorted(by_type.get('distribution',{})):
        dist=latest('distribution',did)
        for it in dist['payload']['entries']:
            add_stmt(it['batch'],it['region'],it['status'],'distribution',did,dist['version'],
                     dist['source'],dist['origin'])
    for (batch,region),stmts in sorted(statements.items()):
        statuses={s['status'] for s in stmts}
        if 'confirmed' in statuses and 'cleared' in statuses:
            conflicts.append({'kind':'batch_status','batch':batch,'region':region,'statements':stmts})

    media_out=[]
    for mid in sorted(by_type.get('media',{})):
        m=latest('media',mid)
        media_out.append({'id':mid,'version':m['version'],'publisher':m['payload'].get('publisher'),
            'product':m['payload'].get('product'),'group_quantities':m['payload']['group_quantities'],
            'source':m['source'],'origin':m['origin'],'recorded_at':m.get('recorded_at'),
            'note':'组级数量仅作线索,不展开为批号'})

    not_applied=[{'id':c['id'],'version':c['version'],'target':c['payload']['target'],
                  'source':c['source'],'reason':'目标版次当前未生效'}
                 for c in corrections if (c['id'],c['version']) not in applied]

    reasons=[]
    for e in notices_out:
        reasons.extend(e['gaps'])
        for cell in e['pending_ranges']:
            reasons.append('批号范围仍待确认:%s/%s'%(cell['batch'],cell['region']))
    for c in conflicts:
        if c['kind']=='batch_status':
            reasons.append('来源表述冲突:%s/%s'%(c['batch'],c['region']))
        else:
            reasons.append('公告与注册信息不一致:'+c['notice'])
    return {'as_of':as_of,'publishable':not reasons,'reasons':reasons,
            'notice_versions':[e['version'] for e in notices_out],
            'notices':notices_out,'conflicts':conflicts,'media_claims':media_out,
            'corrections_not_applied':not_applied}
