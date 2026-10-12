"""Circuit draft and identity checks. Date: 2026-10-12."""
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

    def test_pick_phase_reuses_detected_wire_and_opens_real_circuit_panel(self):
        for name in ('generation','fixed','diagram-update','diagram-commands'):
            self.h.load_definitions(simple.adapter.ROOT/'src'/f'{name}.lsp')
        self.plan(); picks=iter([['panel',[0.,0.,0.]],['w1',[1.,0.,0.]]]); prompts=[]; panels=[]
        steps=[]
        def pick(kind,prompt):
            steps.append('panel'); prompts.append(prompt); return next(picks)
        def number(prompt): steps.append('number'); return None
        self.h.builtins['NENTSEL']=number
        catalog=self.call('EL:DLCatalogInitial','LIB-PANEL')
        entry=self.call('EL:DLEntryNew',catalog,'LAMP')
        values={'display':'Lamp','watts':5,'ground-confirmed':True,'active':True,'status':Symbol('READY'),
                'asset-revision':1,'block-file':'assets/ELDEV1/1/block.dwg',
                'legend-file':'assets/ELDEV1/1/legend.sld','legend-size':[800,600],'legend-checksum':'sld-123-31'}
        for key,value in values.items(): entry=self.call('EL:Put',Symbol(key.upper()),value,entry)
        catalog=self.call('EL:DLUpsert',catalog,entry)
        snapshot=self.call('EL:Put',Symbol('ROOT'),'library-fixture/',
          self.call('EL:Put',Symbol('CATALOG'),catalog,
            self.call('EL:Put',Symbol('INDEX'),self.call('EL:DLIndex',catalog),None)))
        self.h.builtins.update({'EL:ENSUREROOT':lambda:True,'EL:PICKMODEL':pick,
          'EL:LOADCONFIG':lambda:self.cfg,'EL:PRESETLOAD':lambda:self.cfg,
          'HANDENT':lambda e:e if e in self.entities else None,'CHR':chr,
          'EL:DLSNAPSHOT':lambda:snapshot,
          'EL:SIMPLELOADPOWERS':lambda:self.call('EL:Put',Symbol('VERSION'),1,self.call('EL:Put',Symbol('POWERS'),self.call('EL:Put','LAMP',5,None),None)),
          'GETVAR':lambda key:{'FINGERPRINTGUID':'guid','CDATE':20261009.12,'MILLISECS':100}.get(key),
          'EL:REVIEWFIXEDEXITS':lambda result,record:result,
          'EL:PANELDIALOG':lambda result,cfg,powers,cap:panels.append(self.call('EL:PanelCompute',result,powers,cfg)) and None,
          'EL:CLEARPICKHIGHLIGHTS':lambda:None})
        self.h.run('(EL:FixedStatPick)')
        self.assertEqual(steps,['panel','number'])
        self.assertEqual(self.get('panel-number',panels[0]), '暂无编号')
        self.assertEqual(len(prompts),1);self.assertEqual(len(panels),1)
        self.assertEqual(len(self.get('circuits',panels[0])),1)
        self.assertEqual(self.get('box-watts',panels[0]),10)

    def test_saved_incoming_exclusion_and_candidate_change_are_explicit(self):
        self.h.run('''(setq result '((snapshot) (circuits ((id . "R1") (seed (key "W1" outlet)) (complete . T))
          ((id . "R2") (seed (key "IN" outlet)) (complete . T)))))
          (setq selected (EL:SelectFixedExits result '(("IN" outlet))))''')
        self.assertEqual(self.h.run("(length (EL:Get 'circuits selected))"),1)
        self.assertEqual(self.h.run("(length (EL:Get 'candidate-keys selected))"),2)
        self.h.run("(setq record (list (cons 'candidate-keys (EL:Get 'candidate-keys selected)) (cons 'excluded-seeds (EL:Get 'excluded-seeds selected))))")
        self.assertEqual(self.h.run("(length (EL:Get 'circuits (EL:ReviewFixedExits (EL:SelectFixedExits result nil) record)))"),1)

    def test_invalid_power_blocks_ground_toggle_and_preserves_input(self):
        self.plan(); result=self.call('EL:SplitNetwork',simple.SimpleFlowTests.network(self),self.cfg)
        self.h.frames[0]['RESULT']=result
        self.h.run("(setq *EL:PanelDraft* result *EL:PanelPowers* nil *EL:PanelIndex* 0 *EL:PanelDevice* 0 *EL:PanelPage* 0 *EL:ThumbPage* 0)")
        tiles={'b_watts0':'12x'}
        self.h.builtins.update({'GET_TILE':lambda key:tiles.get(key,''),'SET_TILE':lambda k,v:tiles.__setitem__(k,v), 'MODE_TILE':lambda *args:None})
        self.h.run('(EL:PanelGround 0 "1")')
        self.assertEqual(tiles['b_watts0'],'12x');self.assertEqual(tiles['p_ground0'],'0')
        self.assertFalse(truth(self.h.run("(EL:Get 'is-ground (car (EL:Get 'circuits *EL:PanelDraft*)))")))

    def test_free_terminal_without_candidates_does_not_block_generation(self):
        self.plan()
        self.line('w1',[1.,0.,0.],[15.,0.,0.],'W')
        self.selected.remove('wr')
        self.selected.remove('remote')
        network=simple.SimpleFlowTests.network(self)
        result=self.call('EL:SplitNetwork',network,self.cfg)
        powers=self.h.run("'((\"LAMP\" . 5))")
        result=self.call('EL:PanelCompute',result,powers,self.cfg)
        self.assertTrue(truth(self.get('can-generate',result)))
        self.assertEqual(self.get('box-watts',result),10)

    def test_rejected_and_ambiguous_gap_evidence_still_blocks(self):
        issues=self.h.run("(list (EL:Issue 'NO_CANDIDATE \"21FC\" '((candidates) (rejected))) (EL:Issue 'NO_CANDIDATE \"bad\" '((rejected ((reason . BLOCKED_BY_DEVICE_OR_PATH))))) (EL:Issue 'AMBIGUOUS_CANDIDATES \"amb\" nil))")
        kept=self.call('EL:SimpleBlockingGapIssues',issues)
        self.assertEqual([self.get('object',x) for x in kept],['bad','amb'])
