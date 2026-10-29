"""Original-only dialogue path and lifecycle controls with synthetic services."""
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from original_dialogue_pba import DialoguePba,bits
from test_pba101_research import payload


@unittest.skipUnless(os.environ.get('PSYCHONAUTS_REFERENCE'),'owned original required')
class DialogueOriginalTests(unittest.TestCase):
    def setUp(self):
        self.path='Anims/Milla/MITU/LipSync/MITU066MI.pba'
        self.h=DialoguePba(os.environ['PSYCHONAUTS_REFERENCE'],payload([('A',[255]*60)]),['A'],self.path)

    def test_original_babble_selects_actor_resource_before_sound(self):
        h=self.h;s=h.babble();self.assertEqual(s['skeletal_owner'],0);self.assertEqual(s['loop'],0);self.assertEqual(s['weight'],0);self.assertEqual(s['fade_rate'],10)
        self.assertEqual(h.events[0]['this'],h.mesh);self.assertEqual(h.events[1]['this'],h.manager)
        self.assertEqual(h.events[0]['path'],self.path)
        audio=next(i for i,e in enumerate(h.events) if e['event']=='audio-start');self.assertGreater(audio,1)
        self.assertEqual(h.events[audio]['facial_count'],1);self.assertEqual(h.result_handles,[77]);self.assertEqual(h.result_numbers,[1])

    def test_delta_clock_and_fade_in(self):
        h=self.h;h.babble();a=h.step(.05);b=h.step(.05)
        self.assertAlmostEqual(a['state']['seconds'],.05);self.assertAlmostEqual(a['weights'][0],.5)
        self.assertAlmostEqual(b['state']['seconds'],.1);self.assertAlmostEqual(b['weights'][0],1)

    def test_special_mode_suppresses_priority_and_pauses_clock(self):
        h=self.h;h.babble();h.mode=1;a=h.step(.2)
        self.assertEqual(a['state']['seconds'],0);self.assertEqual(a['weights'],[0]);h.mode=0
        self.assertAlmostEqual(h.step(.1)['weights'][0],1)

    def test_stop_fade_and_lazy_cleanup(self):
        h=self.h;h.babble();h.step(.1);s=h.stop(.1);self.assertEqual(s['active'],0)
        self.assertAlmostEqual(h.step(.05)['weights'][0],.5);self.assertEqual(h.step(.06)['weights'],[0])
        h.call(0x48e870,h.manager);self.assertEqual(h.dword(h.manager+0xc),0);self.assertEqual(h.output(),[0])

    def test_babble_stop_wrapper_rebuilds_same_path_without_stopping_audio(self):
        h=self.h;h.babble();h.step(.1);h.lua_count=3;h.lua_strings={2:h.namespace,3:h.line}
        h.call(0x598970,0,(0x12345678,));self.assertEqual(h.snapshot()['active'],0)
        event=next(e for e in h.events if e['event']=='actor-stop')
        self.assertEqual(event['path'],self.path);self.assertEqual(event['fade'],-1)
        self.assertEqual(h.snapshot()['fade_rate'],10)
        self.assertAlmostEqual(h.step(.05)['weights'][0],.5)
        self.assertEqual(sum(e['event']=='audio-start' for e in h.events),1)

    def test_script_stop_default_fades_and_zero_removal_requires_cache_identity(self):
        h=self.h;h.babble();h.step(.1);h.lua_count=2;h.lua_strings={2:h.string(self.path)}
        h.call(0x5bffe0,0,(0x12345678,));self.assertEqual(h.snapshot()['active'],0)
        self.assertAlmostEqual(h.step(.05)['weights'][0],.5)
        h.lua_count=3;h.lua_numbers={3:0.};h.call(0x5bffe0,0,(0x12345678,))
        self.assertEqual(h.dword(h.manager+0xc),1)  # Cache miss does not remove.
        # Synthetic cache identity tests the other original branch; it does not
        # claim that the real asynchronous resource cache was reconstructed.
        h.lookup_result=h.alloc(0x20);h.write(h.obj+0x10,h.lookup_result)
        h.call(0x5bffe0,0,(0x12345678,))
        self.assertEqual(h.dword(h.manager+0xc),0);self.assertEqual(h.output(),[0])

    def test_terminal_clear_and_natural_release(self):
        h=DialoguePba(os.environ['PSYCHONAUTS_REFERENCE'],payload([('A',[255]*3)]),['A'],self.path);h.babble()
        self.assertEqual(h.step(.1)['weights'],[0]);self.assertEqual(h.snapshot()['complete'],1)
        for _ in range(10):h.step(.05)
        self.assertEqual(h.dword(h.manager+0xc),0);self.assertEqual(h.output(),[0])

    def test_skeletal_owner_bypasses_delta_and_accepts_external_clock(self):
        h=self.h;h.babble();owner=h.alloc(0x60);h.call(0x48d290,h.state,(owner,));self.assertEqual(h.step(.1)['state']['seconds'],0)
        h.call(0x48d2b0,h.state,(1,bits(.25),bits(.5)))
        self.assertAlmostEqual(h.output()[0],.25);self.assertAlmostEqual(h.snapshot()['seconds'],.5)
        self.assertAlmostEqual(h.step(.1)['state']['seconds'],.5)

    def test_composition_takes_max_with_base_weights(self):
        h=self.h;h.babble();h.write(h.manager+0x124,bits(.7))
        self.assertAlmostEqual(h.step(.05)['weights'][0],.7,places=6)
        self.assertAlmostEqual(h.step(.05)['weights'][0],1)

    def test_missing_lipsync_falls_back_then_starts_audio(self):
        h=self.h;h.path='unavailable';self.assertIsNone(h.babble())
        starts=[e for e in h.events if e['event']=='0x43a060'];self.assertEqual(len(starts),2)
        self.assertEqual(starts[1]['path'],'Anims/Milla/MITU/Babble.pba');self.assertEqual(starts[1]['args'][1],1)
        self.assertTrue(any(e['event']=='audio-start' for e in h.events));self.assertEqual(h.result_numbers,[0])

    def test_player_path_includes_line_prefix_directory(self):
        h=self.h;h.write(h.game+0x818c,h.actor);h.path='Anims/Milla/MITU/LipSync/MI/MITU066MI.pba';h.babble()
        self.assertEqual(h.events[0]['path'],h.path)

    def test_manual_load_flags_and_replacement(self):
        h=self.h;h.babble();s=h.manual(self.path,loop=True,replace=True,fade=.2)
        self.assertEqual(s['controllers'],1);self.assertEqual(s['loop'],1);self.assertAlmostEqual(s['fade_rate'],5)
        self.assertEqual(h.uc.mem_read(h.state+0x111,1),b'\0')


if __name__=='__main__':unittest.main()
