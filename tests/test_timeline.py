"""按观察时间回放召回范围:更正作用域、媒体组级数量、冲突与待补状态。"""
import hashlib
import json
import unittest
from pathlib import Path
from capture_service.transport import Replay
from capture_service.ledger import connect,receive
from capture_service.view import overview

ROOT=Path(__file__).resolve().parents[1]
COLLECTION='recall-issuer'
FIRM='https://firm.example.test'
REGULATOR='https://regulator.example.test'

def confirmed(view):
    return {(r['batch'],r['region']) for n in view['notices'] for r in n['confirmed_ranges']}

def notice(view):
    return view['notices'][0]

class Timeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        replay=Replay(ROOT/'data'/'timeline.json')
        cls.db=connect(':memory:')
        for step in replay.steps:
            request=step['request']
            raw,receipt=replay.request(request['method'],request['url'])
            receive(cls.db,COLLECTION,raw,receipt)
        cls.steps=len(replay.steps)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def view(self,as_of=None):
        return overview(self.db,COLLECTION,as_of)

    def test_ingest_is_idempotent_and_append_only(self):
        # 15 次抓取中只有 13 份不同原文;回退与重复抓取不产生新记录
        self.assertEqual(self.steps,15)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],13)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM entities').fetchone()[0],13)

    def test_replay_before_supplements(self):
        view=self.view('2026-11-17T09:03:00Z')
        self.assertEqual(notice(view)['version'],'v1')
        self.assertIn('附件清单未接收:L-4',notice(view)['gaps'])
        self.assertIn('产品注册信息未接收:R-9',notice(view)['gaps'])
        self.assertEqual(confirmed(view),set())
        view=self.view('2026-11-17T09:30:00Z')
        self.assertNotIn('附件清单未接收:L-4',notice(view)['gaps'])
        self.assertIn('产品注册信息未接收:R-9',notice(view)['gaps'])
        view=self.view('2026-11-17T23:00:00Z')
        self.assertNotIn('产品注册信息未接收:R-9',notice(view)['gaps'])
        self.assertEqual(confirmed(view),set())
        self.assertEqual({(r['batch'],r['region']) for r in notice(view)['pending_ranges']},
                         {('B-04','华东')})
        self.assertFalse(view['publishable'])

    def test_replay_sees_unreferenced_newer_annex(self):
        # 批号附件 v2 已接收但附件清单仍钉住 v1:不提前生效,只记备注
        view=self.view('2026-11-18T10:30:00Z')
        self.assertEqual(confirmed(view),set())
        self.assertTrue(any('v2' in note for note in notice(view)['notes']))
        view=self.view('2026-11-18T12:30:00Z')
        self.assertEqual(confirmed(view),{('B-04','华东')})
        self.assertIn('流通清单未接收:D-4@v1',notice(view)['gaps'])

    def test_late_distribution_list_flips_pending_gap(self):
        before=self.view('2026-11-18T23:00:00Z')
        self.assertIn('流通清单未接收:D-4@v1',notice(before)['gaps'])
        after=self.view('2026-11-19T23:00:00Z')
        self.assertNotIn('流通清单未接收:D-4@v1',notice(after)['gaps'])
        dist={(d['batch'],d['region']):d['status'] for d in notice(after)['distribution']}
        self.assertEqual(dist,{('B-04','华东'):'confirmed',('B-04','华北'):'pending_confirmation'})

    def test_correction_only_covers_named_scope(self):
        view=self.view('2026-11-20T09:30:00Z')
        self.assertEqual(confirmed(view),{('B-04','华东'),('B-05','华东')})
        self.assertTrue(view['publishable'])
        final=self.view()
        cells={(r['batch'],r['region']):r for r in notice(final)['confirmed_ranges']}
        # C-1 只增加其明确列出的 B-05/华东,来源可追溯到更正原文
        self.assertEqual(cells[('B-05','华东')]['via'],'correction:C-1')
        # C-2 指向未生效的 A-4@v1,不影响现行 v2 的 B-04/华东
        self.assertEqual(cells[('B-04','华东')]['status'],'confirmed')
        self.assertEqual([c['id'] for c in final['corrections_not_applied']],['C-2'])
        # C-3 只覆盖其列出的公告字段:生效日期被更正,产品名不变
        self.assertEqual(notice(final)['effective'],'2026-11-19')
        self.assertEqual(notice(final)['product'],'一捻金')

    def test_confirmed_cells_carry_source_and_observation_time(self):
        view=self.view()
        cells={(r['batch'],r['region']):r for r in notice(view)['confirmed_ranges']}
        annex_v2=hashlib.sha256((ROOT/'data'/'tl-annex-a4-v2.bin').read_bytes()).hexdigest()
        corr_c1=hashlib.sha256((ROOT/'data'/'tl-correction-c1.bin').read_bytes()).hexdigest()
        self.assertEqual(cells[('B-04','华东')]['source'],annex_v2)
        self.assertEqual(cells[('B-04','华东')]['recorded_at'],'2026-11-18T10:00:00Z')
        self.assertEqual(cells[('B-05','华东')]['source'],corr_c1)
        self.assertEqual(cells[('B-05','华东')]['recorded_at'],'2026-11-20T09:00:00Z')

    def test_media_group_quantities_never_become_batches(self):
        view=self.view()
        self.assertEqual([m['id'] for m in view['media_claims']],['M-1'])
        scoped=[r for n in view['notices'] for r in
                n['confirmed_ranges']+n['pending_ranges']+n['cleared_ranges']]
        self.assertTrue(scoped)
        self.assertTrue(all(r['id']!='M-1' for r in scoped))
        # 媒体若给出批号级范围,接收时直接拒绝且不入账
        raw=json.dumps({'media':'M-9','group_quantities':[],
                        'ranges':[{'batch':'B-99','region':'华东','status':'confirmed'}]},
                       ensure_ascii=False).encode('utf-8')
        receipt={'url':FIRM+'/reports/m-9','status':200,
                 'body_sha256':hashlib.sha256(raw).hexdigest(),'observed_at':None}
        db=connect(':memory:')
        with self.assertRaises(ValueError):receive(db,COLLECTION,raw,receipt)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],0)
        db.close()

    def test_firm_regulator_conflict_is_kept(self):
        view=self.view()
        self.assertFalse(view['publishable'])
        self.assertIn('来源表述冲突:B-05/华东',view['reasons'])
        conflict=[c for c in view['conflicts']
                  if c['kind']=='batch_status' and c['batch']=='B-05'][0]
        by_origin={s['origin']:s['status'] for s in conflict['statements']}
        self.assertEqual(by_origin[FIRM],'confirmed')
        self.assertEqual(by_origin[REGULATOR],'cleared')
        self.assertTrue(all(s['source'] for s in conflict['statements']))

    def test_rollback_and_rescrape_do_not_erase_later_evidence(self):
        before=overview(self.db,COLLECTION,'2026-11-21T23:59:59Z')
        after=overview(self.db,COLLECTION,None)
        strip=lambda v:{k:x for k,x in v.items() if k!='as_of'}
        self.assertEqual(strip(before),strip(after))
        self.assertEqual(confirmed(after),{('B-04','华东'),('B-05','华东')})

if __name__=='__main__':
    unittest.main()
