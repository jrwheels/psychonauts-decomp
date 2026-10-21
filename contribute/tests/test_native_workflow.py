import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'contribute/tools'))
from native_workflow import rank, plan, record_attempt, validate_cache, safe_output, sha, fingerprint
from native_index import validate_evidence, REFERENCE_SHA256


def record(va, size=60, status=None, calls=(), **extra):
    return dict(va=va, mapped_size=size, csv_status=status, callees=[{'target_va':x} for x in calls], callers=[], **extra)


class WorkflowTests(unittest.TestCase):
    def test_deterministic_and_actual_dependencies(self):
        records=[record(3, calls=[1,None,99]), record(2), record(1,status='matching')]
        ranked=rank(records)
        self.assertEqual(ranked,rank(list(reversed(records))))
        three=next(r for r in ranked if r['va']==3)
        self.assertEqual(three['direct_dependencies'],[1,99])
        self.assertEqual(three['unknown_dependencies'],[99])
        self.assertEqual(three['indirect_calls'],1)
        self.assertEqual(three['components']['known'],8)

    def test_independence_and_strategic_lanes(self):
        ranked=rank([record(1,calls=[2]),record(2),record(3,300),record(4,1000)])
        batches=plan(ranked)
        self.assertEqual([b['lane'] for b in batches],['small','medium','complex'])
        self.assertEqual(len(batches[0]['targets']),1)
        self.assertIsNone(batches[0]['targets'][0]['symbol'])

    def test_retry_requires_changed_context_or_explicit_override(self):
        e={};record_attempt(e,'0x00000001','layout','a'*64,'blocked',2.5)
        before=copy.deepcopy(e)
        with self.assertRaisesRegex(ValueError,'unchanged'):
            record_attempt(e,'0x00000001','layout','a'*64,'blocked')
        self.assertEqual(e,before)
        record_attempt(e,'0x00000001','layout','b'*64,'blocked')
        record_attempt(e,'0x00000001','layout','b'*64,'blocked',retry=True)
        self.assertNotIn('milestones',e['functions']['0x00000001'])

    def test_fingerprint_tracks_source_and_caller_context(self):
        r=record(1);r['callers']=[]
        a=fingerprint(r,'a'*64,{}, {'a.cpp':'1'})
        self.assertNotEqual(a,fingerprint(r,'a'*64,{}, {'a.cpp':'2'}))
        r['callers']=[{'function_va':2}]
        self.assertNotEqual(a,fingerprint(r,'a'*64,{}, {'a.cpp':'1'}))

    def test_cache_rejects_stale_identity_and_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);outputs={}
            for name in ['binary.json','functions.json','lua-native.json']:
                (p/name).write_text('[]');outputs[name]=sha(b'[]')
            (p/'manifest.json').write_text(json.dumps(dict(inputs={'binary_sha256':REFERENCE_SHA256},outputs=outputs)))
            self.assertEqual(validate_cache(p,{'binary_sha256':REFERENCE_SHA256}),[])
            with self.assertRaisesRegex(ValueError,'inputs'):validate_cache(p,{'binary_sha256':'wrong'})
            (p/'functions.json').write_text('[1]')
            with self.assertRaisesRegex(ValueError,'output'):validate_cache(p,{'binary_sha256':REFERENCE_SHA256})

    def test_schema_rejects_malformed_workflow(self):
        for workflow in [[], {'attempts':1}, {'blockers':['']}, {'next_action':False},
                         {'attempts':[{'method':'x','fingerprint':'z'*64,'outcome':'blocked'}]},
                         {'attempts':[{'method':'x','fingerprint':'a'*64,'outcome':'blocked','elapsed_seconds':True}]}]:
            with self.assertRaises(ValueError):
                validate_evidence(dict(schema_version=1,binary_sha256=REFERENCE_SHA256,functions={'0x00000001':{'workflow':workflow}}),{1})

    def test_output_rejects_tracked_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'build').mkdir();(root/'docs').mkdir()
            with self.assertRaises(ValueError):safe_output(root/'docs/x',root)
            (root/'build/link').symlink_to(root/'docs',target_is_directory=True)
            with self.assertRaises(ValueError):safe_output(root/'build/link/x',root)
            self.assertEqual(safe_output(root/'build/x',root),root/'build/x')

    def test_focus_uses_observed_neighbors_and_does_not_invent_source(self):
        records=[record(1,status='matching',source='src/game/mesh.cpp',calls=[2]),
                 record(2,calls=[3]),record(3),record(4)]
        ranked=rank(records,'mesh')
        by_va={r['va']:r for r in ranked}
        self.assertEqual(by_va[2]['focus_distance'],1)
        self.assertEqual(by_va[3]['focus_distance'],2)
        self.assertIsNone(by_va[4]['focus_distance'])
        self.assertIsNone(by_va[2]['source'])

    def test_deferred_and_unchanged_failed_candidates_are_not_scheduled(self):
        ranked=rank([record(1,workflow={'deferred':True}),record(2),record(3)])
        next(r for r in ranked if r['va']==2)['retry_suppressed']=True
        targets=[t['address'] for batch in plan(ranked) for t in batch['targets']]
        self.assertEqual(targets,['0x00000003'])
