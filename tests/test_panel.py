"""Circuit draft and identity checks. Date: 2026-10-09."""
import unittest
import test_simple_flow as simple
from autolisp_host import Symbol, truth

class PanelTests(unittest.TestCase):
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block
    plan = simple.SimpleFlowTests.plan
    def setUp(self):
        simple.SimpleFlowTests.setUp(self)
        self.h.load_definitions(simple.adapter.ROOT/'src/panel.lsp')

    def test_two_pick_network_is_split_without_sharing_panel(self):
        self.plan()
        self.block('LAMP','D','c',[0.,10.,0.])
        self.line('out2',[0.,1.,0.],[0.,9.,0.],'W')
        self.selected += ['c','out2']
        result=self.call('EL:SplitNetwork',simple.SimpleFlowTests.network(self),self.cfg)
        cs=self.get('circuits',result)
        self.assertEqual(len(cs),2)
        self.assertEqual(sorted(sorted(self.get('devices',c)) for c in cs),[['a','b'],['c']])
        self.h.frames[0]['RESULT']=result
        self.assertTrue(truth(self.h.run("(EL:Get 'can-generate (EL:PanelCompute result '((\"LAMP\" . 5)) cfg))")))
        self.assertEqual(self.h.run("(EL:Get 'box-watts (EL:PanelCompute result '((\"LAMP\" . 5)) cfg))"),15)

    def test_uid_order_and_manual_no_survive_renumbering(self):
        self.assertTrue(truth(self.h.run('''(setq saved '(((seed-key "W1" outlet) (circuit-uid . "u1")
          (output-order . 1) (is-ground) (ground-source . manual))))
          (setq matched (EL:MatchCircuits '(((id . "R9") (seed (key "W1" outlet)))) saved "d"))
          (setq c (car (EL:Get 'circuits matched)))
          (and (equal (EL:Get 'circuit-uid c) "u1") (not (EL:Get 'is-ground c))
            (equal (EL:Get 'ground-source c) 'manual) (not (EL:Get 'ambiguous matched))
            (EL:Get 'ambiguous (EL:MatchCircuits '(((id . "R9") (seed (key "W2" outlet)))) saved "d"))
            (not (EL:Get 'is-ground (EL:GroundSuggestion c '("lamp") "v1" nil))))''')))

    def test_missing_power_overlimit_and_zero(self):
        self.plan()
        result=self.call('EL:SplitNetwork',simple.SimpleFlowTests.network(self),self.cfg)
        self.h.frames[0]['RESULT']=result
        for power in ('nil', '\'(("LAMP" . 100))'):
            self.assertFalse(truth(self.h.run(f"(EL:Get 'can-generate (EL:PanelCompute result {power} cfg))")))
        self.assertTrue(truth(self.h.run('(EL:Get \'can-generate (EL:PanelCompute result \'(("LAMP" . 0)) cfg))')))
