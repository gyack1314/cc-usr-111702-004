"""解释企业公告及附件中的范围。"""
import json
def decode(raw,receipt):
    d=json.loads(raw.decode('utf-8'))
    if 'notice' in d:
        return [{'type':'notice','id':d['notice'],'version':d['revision'],
                 'payload':{'effective':d['effective'],'product':d['product'],'annex':d['annex']}}]
    if 'annex' in d:
        return [{'type':'annex','id':d['annex'],'version':d['revision'],
                 'payload':{'ranges':d['ranges']}}]
    raise ValueError('企业召回资料非法')
def assess(rows):
    notices=[r for r in rows if r['type']=='notice'];annexes={r['id']:r for r in rows if r['type']=='annex'}
    reasons=[]
    for n in notices:
        a=annexes.get(n['payload']['annex'])
        if not a:reasons.append('批号附件未接收:'+n['payload']['annex'])
        elif a['version']!=n['version']:reasons.append('公告附件版次不一致')
        elif any(r['status']!='confirmed' for r in a['payload']['ranges']):reasons.append('批号范围仍待确认')
    return {'publishable':not reasons,'reasons':reasons,'notice_versions':[r['version'] for r in notices]}
