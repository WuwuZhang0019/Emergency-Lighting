"""Normal device branches and blocking faults. Date: 2026-10-09."""
import unittest
from autolisp_host import Symbol, truth
import test_panel as panel
import test_simple_flow as simple
import test_contact_index as contact


class DeviceBranchTests(unittest.TestCase):
    setUp = panel.PanelTests.setUp
    call = panel.PanelTests.call
    get = panel.PanelTests.get
    line = panel.PanelTests.line
    block = panel.PanelTests.block

    def test_three_wire_device_branch_counts_downstream_and_allows_generation(self):
        for name, point in [('panel', [0., 0., 0.]), ('a', [10., 0., 0.]),
                            ('b', [20., 0., 0.]), ('c', [10., 10., 0.])]:
            self.block('BOX' if name == 'panel' else 'LAMP',
                       'P' if name == 'panel' else 'D', name, point)
        self.line('w1', [1., 0., 0.], [9., 0., 0.], 'W')
        self.line('w2', [11., 0., 0.], [19., 0., 0.], 'W')
        self.line('w3', [10., 1., 0.], [10., 9., 0.], 'W')
        self.selected = ['panel', 'a', 'b', 'c', 'w1', 'w2', 'w3']
        result = self.call('EL:SplitNetwork', simple.SimpleFlowTests.network(self), self.cfg)
        circuit = self.get('circuits', result)[0]
        self.assertEqual(sorted(self.get('devices', circuit)), ['a', 'b', 'c'])
        self.assertTrue(truth(self.get('complete', circuit)))
        self.h.frames[0]['RESULT'] = result
        computed = self.h.run('(EL:PanelCompute result \'(("LAMP" . 5)) cfg)')
        self.assertTrue(truth(self.get('can-generate', computed)))
        self.assertEqual(self.get('box-watts', computed), 15)

    def test_loop_and_other_panel_still_block(self):
        for edges in ['(("W" "D") ("D" "X") ("X" "W"))',
                      '(("W" "D") ("D" "P"))']:
            result = self.h.run('''(EL:TraceCircuit '((id . "R1") (wire . "W"))
                '((blocks ((id . "D") (role . device)) ((id . "P") (role . panel))))
                '%s nil)''' % edges)
            self.assertFalse(truth(self.get('complete', result)))


class PhysicalBranchTests(unittest.TestCase):
    setUp = contact.ContactIndexTests.setUp
    call = contact.ContactIndexTests.call
    get = contact.ContactIndexTests.get
    line = contact.ContactIndexTests.line
    record = contact.ContactIndexTests.record
    polygon = staticmethod(contact.ContactIndexTests.polygon)
    block_record = contact.ContactIndexTests.block_record
    wire = contact.ContactIndexTests.wire
    snapshot = contact.ContactIndexTests.snapshot

    def test_three_verified_contacts_are_not_abnormal(self):
        block = self.block_record('D', [self.polygon([(-1., -1.), (1., -1.), (1., 1.), (-1., 1.)])])
        wires = [self.wire('A', [-5., 0., 0.], [-1., 0., 0.]),
                 self.wire('B', [1., 0., 0.], [5., 0., 0.]),
                 self.wire('C', [0., 1., 0.], [0., 5., 0.])]
        result = self.call('EL:BuildPhysical', self.snapshot(wires, [block]), self.h.lookup('CFG'), None)
        self.assertNotIn(Symbol('ABNORMAL_BRANCH'),
                         [self.get('code', issue) for issue in self.get('issues', result) or []])
        self.assertEqual(len(self.get('edges', result)), 3)


if __name__ == '__main__':
    unittest.main()
