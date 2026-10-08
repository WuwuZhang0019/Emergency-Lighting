"""Whole INSERT policy. Date: 2026-10-08; synthetic CAD adapter only."""
import unittest
from autolisp_host import Symbol, truth
import test_box as box

class WholeBlockTests(unittest.TestCase):
    setUp = box.BoxTests.setUp
    call = box.BoxTests.call
    get = box.BoxTests.get
    block = box.BoxTests.block
    line = box.BoxTests.line
    record = box.BoxTests.record
    analyze = box.BoxTests.analyze
    path_hit = box.BoxTests.path_hit

    def test_collection_never_reads_internal_geometry_or_builds_contour_tree(self):
        self.block('BOX', 'P', 'panel', [0., 0., 0.])
        self.block('LAMP', 'D', 'lamp', [10., 0., 0.])
        self.line('w', [1., 0., 0.], [9., 0., 0.], 'W')
        self.selected = ['panel', 'lamp', 'w']
        def forbidden(*args):
            self.fail('Whole blocks must never inspect internal geometry')
        for name in ('ENTNEXT','EL:DEFINITIONDATA','EL:BLOCKCONTOUR','EL:CLOSEDRINGS',
                     'EL:PREPARECONTOURCONTACT','EL:CONTOURTREE','EL:INSERTMATRIX'):
            self.h.builtins[name] = forbidden
        result = self.analyze()
        self.assertTrue(truth(self.get('complete', result)))
        self.assertEqual(self.get('devices', self.get('circuits', result)[0]), ['lamp'])
        self.assertTrue(all(len(self.get('segments', b)) == 4 for b in self.get('blocks', self.get('snapshot', result))))

    def test_middle_crossing_tangent_and_inside_hit_but_aabb_only_overlap_does_not(self):
        self.block('LAMP','D','b',[0.,0.,0.]); b=self.record('b')
        for a,c in [([-5.,0.,0.],[5.,0.,0.]),([-5.,1.,0.],[5.,1.,0.]),([0.,0.,0.],[.5,.5,0.])]:
            self.assertTrue(self.path_hit(a,c,b))
        self.assertFalse(self.path_hit([-3.,0.,0.],[0.,3.,0.],b))
        self.assertFalse(self.path_hit([-5.,0.,2.],[5.,0.,2.],b))

    def test_panel_middle_crossing_is_one_seed_and_device_connection(self):
        self.block('BOX','P','panel',[0.,0.,0.])
        self.block('LAMP','D','lamp',[8.,0.,0.])
        self.block('LAMP','D','left',[-6.,0.,0.])
        self.line('w',[-5.,0.,0.],[7.,0.,0.],'W')
        self.selected=['panel','lamp','left','w']
        result=self.analyze(); circuits=self.get('circuits',result)
        self.assertEqual(len(circuits),1)
        self.assertEqual(sorted(self.get('devices',circuits[0])),['lamp','left'])
        self.assertTrue(truth(self.get('complete', result)))
        self.assertNotIn(Symbol('PANEL_PATH_CROSSING'),[self.get('code',i) for i in self.get('issues', result) or []])

    def test_missing_bounds_is_explicit_and_never_expands(self):
        self.block('LAMP','D','b',[0.,0.,0.]); self.bounds.pop('b')
        b=self.record('b')
        self.assertEqual(self.get('code',self.get('issues',b)[0]),Symbol('MISSING_BLOCK_BOUNDS'))
        self.assertFalse(self.get('segments',b))
        self.assertFalse(self.path_hit([-5.,0.,0.],[5.,0.,0.],b))

    def test_bounds_change_invalidates_source_signature(self):
        self.block('LAMP','D','b',[0.,0.,0.]); before=self.record('b')
        self.bounds['b']=[[-2.,-2.,0.],[2.,2.,0.]]
        after=self.record('b')
        self.assertEqual(self.get('identity',before),self.get('identity',after))
        self.assertNotEqual(self.get('raw',before),self.get('raw',after))

    def test_gap_indexes_one_row_for_whole_block_and_blocks_crossing(self):
        self.block('LAMP','D','b',[0.,0.,0.]); b=self.record('b')
        self.h.frames[0]['B']=b
        tree=self.h.run("(EL:GapPathIndex (list (cons 'blocks (list b))))")
        self.assertTrue(self.get('whole-block',tree[0]))
        self.assertFalse(tree[1]); self.assertFalse(tree[2])
        blockers=self.h.run("(EL:GapBlocked '((point -5.0 0.0 0.0)) '((point 5.0 0.0 0.0)) (list (cons 'blocks (list b))) nil)")
        self.assertEqual(blockers,['b'])
