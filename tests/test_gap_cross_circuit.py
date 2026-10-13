"""Cross-device gap continuation and circuit isolation. Date: 2026-10-13.
Synthetic CAD adapters; native drawing acceptance remains pending.
"""
import unittest
from autolisp_host import Pair, Symbol, truth
import test_simple_flow as simple


class CrossCircuitGapTests(unittest.TestCase):
    call = simple.SimpleFlowTests.call
    get = simple.SimpleFlowTests.get
    line = simple.SimpleFlowTests.line
    block = simple.SimpleFlowTests.block
    network = simple.SimpleFlowTests.network
    gap_plan = simple.SimpleFlowTests.gap_plan

    def setUp(self):
        simple.SimpleFlowTests.setUp(self)
        self.h.load_definitions(simple.adapter.ROOT/'src/panel.lsp')

    def split(self):
        result = self.call('EL:SplitNetwork', self.network(), self.cfg)
        self.assertTrue(truth(self.get('complete', result)), self.get('circuits', result))
        return self.get('circuits', result)

    def test_1430_gap_crosses_other_circuit_device_and_wire_without_merging(self):
        self.gap_plan((1530.,0.,0.),(1700.,0.,0.),(1701.,0.,0.))
        self.line('before',[1.,0.,0.],[100.,0.,0.],'W')
        self.block('LAMP','D','foreign',[800.,0.,0.])
        points = [(0.,-1.),(0.,-100.),(800.,-100.),(800.,-1.)]
        self.entities['foreign-wire'] = [Pair(0,'LWPOLYLINE'),Pair(5,'foreign-wire'),Pair(8,'W'),
            Pair(410,'Model'),Pair(90,len(points)),Pair(70,0),Pair(38,0.),Pair(210,[0.,0.,1.])] + [
            Pair(10,list(p)) for p in points]
        self.line('cross',[1100.,-20.,0.],[1100.,20.,0.],'W')
        self.selected += ['foreign','foreign-wire','cross']
        network = self.network()
        self.assertEqual(len(self.get('gap-pairs', network) or []),1)
        self.assertEqual(self.get('distance',self.get('metrics',self.get('gap-pairs',network)[0])),1430.)
        circuits = self.split()
        self.assertEqual(len(circuits),2)
        main = next(c for c in circuits if 'before' in self.get('wires',c))
        other = next(c for c in circuits if 'foreign-wire' in self.get('wires',c))
        self.assertEqual(set(self.get('wires',main)),{'before','after-wire'})
        self.assertEqual(self.get('devices',main),['after'])
        self.assertEqual(self.get('devices',other),['foreign'])
        self.assertNotIn('cross',self.get('wires',main))
        self.assertEqual(set(self.get('sources',self.get('number-scope',main))),{'before','after-wire'})
        self.assertEqual(self.get('boundaries',self.get('number-scope',main)),['after'])

    def test_exact_2000_gap_passes_and_longer_gap_does_not(self):
        for distance, accepted in ((2000.,True),(2000.01,False)):
            with self.subTest(distance=distance):
                self.setUp()
                self.gap_plan((10.+distance,0.,0.),(19.+distance,0.,0.),(20.+distance,0.,0.))
                self.block('LAMP','D','foreign',[1000.,0.,0.]);self.selected += ['foreign']
                network=self.network()
                self.assertEqual(bool(self.get('gap-pairs',network)),accepted)
                self.assertEqual([self.get('id',b) for b in self.get('devices',network) or []],['after'] if accepted else [])

    def test_multiple_candidates_across_devices_still_require_mutual_uniqueness(self):
        self.gap_plan()
        snapshot=self.call('EL:SimpleCollect',self.cfg)
        ends=self.get('ends',snapshot)
        a=self.call('EL:By',Symbol('KEY'),['before',Symbol('END')],ends)
        b=self.call('EL:By',Symbol('KEY'),['after-wire',Symbol('START')],ends)
        c=self.call('EL:Put',Symbol('POINT'),[25.,0.,0.],b)
        c=self.call('EL:Put',Symbol('WIRE'),'alternative',c)
        c=self.call('EL:Put',Symbol('KEY'),['alternative',Symbol('START')],c)
        # Isolate the uniqueness gate from earlier physical occupancy/path checks.
        snapshot=[Pair(Symbol('ENDS'),[a,b,c]),Pair(Symbol('BLOCKS'),[
            [Pair(Symbol('ID'),'foreign'),Pair(Symbol('ROLE'),Symbol('DEVICE')),
             Pair(Symbol('WHOLE-BLOCK'),True),Pair(Symbol('BOUNDS'),[[14.,-1.,0.],[16.,1.,0.]])]])]
        rows=self.call('EL:FindGapCandidates',self.call('EL:SimpleGapSnapshot',snapshot),self.cfg)
        pairs=self.call('EL:BuildMutualPairs',rows,snapshot,self.cfg)
        self.assertFalse(self.get('pairs',pairs))
        self.assertIn(Symbol('AMBIGUOUS_CANDIDATES'),[self.get('code',i) for i in self.get('issues',pairs)])

    def test_collinear_path_in_gap_remains_a_blocker(self):
        self.gap_plan()
        # Both endpoints terminate at devices, so the middle wire is not a free candidate.
        self.line('middle',[14.,0.,0.],[16.,0.,0.],'W')
        for name,x in (('left-terminal',14.),('right-terminal',16.)):
            self.block('LAMP','D',name,[x,0.,0.])
        self.selected += ['middle','left-terminal','right-terminal']
        network=self.network()
        self.assertFalse(self.get('gap-pairs',network))
        self.assertFalse(self.get('devices',network))
        reasons=[self.get('reason',r) for issue in self.get('gap-issues',network) or []
            for r in self.get('rejected',self.get('detail',issue)) or []]
        self.assertIn(Symbol('BLOCKED_BY_DEVICE_OR_PATH'),reasons)

    def test_current_panel_still_blocks_gap_continuation(self):
        self.block('BOX','P','panel',[0.,0.,0.])
        self.line('left',[-20.,0.,0.],[-10.,0.,0.],'W')
        self.line('right',[10.,0.,0.],[20.,0.,0.],'W')
        self.selected=['panel','left','right']
        snapshot=self.call('EL:SimpleCollect',self.cfg)
        blocks=[self.call('EL:Put',Symbol('ROLE'),Symbol('PANEL'),b) for b in self.get('blocks',snapshot)]
        snapshot=self.call('EL:Put',Symbol('BLOCKS'),blocks,snapshot)
        snapshot=self.call('EL:SimpleGapSnapshot',snapshot)
        rows=self.call('EL:FindGapCandidates',snapshot,self.cfg)
        row=self.call('EL:By',Symbol('KEY'),['left',Symbol('END')],rows)
        self.assertFalse(self.get('candidates',row))
        self.assertIn(Symbol('BLOCKED_BY_DEVICE_OR_PATH'),[self.get('reason',r) for r in self.get('rejected',row)])

    def test_rule_change_invalidates_results_recognized_with_previous_policy(self):
        rules=self.call('EL:RecognitionRules',self.cfg)
        self.assertEqual(self.get('simple-gap-policy',rules),1)
        old=[r for r in rules if (r.car if isinstance(r,Pair) else r[0]) != Symbol('SIMPLE-GAP-POLICY')]
        snapshot=[Pair(Symbol('SIGNATURE'),'source')]
        result=[Pair(Symbol('DRAWING'),self.get('drawing',self.cfg)),
            Pair(Symbol('RULES'),old),Pair(Symbol('SNAPSHOT'),snapshot)]
        self.assertFalse(truth(self.call('EL:SourceCurrent',result,self.cfg,snapshot)))
