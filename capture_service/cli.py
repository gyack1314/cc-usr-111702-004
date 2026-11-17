"""只读重放合成的来源交互并展示指定观察时间下的接收状态。"""
import argparse
import json
from .transport import Replay
from .ledger import connect,receive
from .view import overview

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['inspect'])
    p.add_argument('manifest')
    p.add_argument('--collection',default='recall-issuer')
    p.add_argument('--as-of',dest='as_of',default=None,
                   help='只回放该观察时间(ISO-8601)之前已接收的版本')
    args=p.parse_args()
    replay=Replay(args.manifest)
    db=connect(':memory:')
    for step in replay.steps:
        request=step['request']
        raw,receipt=replay.request(request['method'],request['url'])
        receive(db,args.collection,raw,receipt)
    print(json.dumps(overview(db,args.collection,args.as_of),ensure_ascii=False,indent=2))
    db.close()

if __name__=='__main__':main()
