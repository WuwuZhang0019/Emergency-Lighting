"""Saved panel data uses the audited DWG store. Date: 2026-10-13.

Finite adapters verify persistence; native AutoCAD acceptance remains separate.
"""
import copy
import unittest

from autolisp_host import truth
import test_diagram_update as updates
import test_incremental_updates as incremental


class HistoryPersistenceTests(unittest.TestCase):
    def test_saved_draft_keeps_its_snapshot_and_formal_source_separate(self):
        fixture = updates.UpdateTests()
        fixture.setUp()
        fixture.install_sync()
        host = fixture.h
        host.run('''
          (setq formal '(EL_FIXED_SOURCE_V1 ((drawing . "old") (wires))))
          (setq source '(EL_FIXED_SOURCE_V1 ((drawing . "new")
            (blocks ((id . "lamp") (name . "灯具"))) (wires))))
          (setq record (EL:Put 'source-signature formal record))
          (EL:StoreWrite (EL:StorePutDiagram record store))
          (setq result (EL:Put 'snapshot (list (cons 'signature source)) result))
        ''')
        self.assertTrue(truth(host.run("(EL:SaveDraft result nil nil 'cap300)")))
        host.run('(setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(host.run("(EL:Get 'source-signature reopened)"), host.lookup('FORMAL'))
        self.assertEqual(host.run("(EL:Get 'draft-source-signature reopened)"), host.lookup('SOURCE'))
        self.assertEqual(host.run("(EL:Get 'draft-circuits reopened)"), host.run("(EL:Get 'circuits result)"))
        # A same-source power edit must not serialize a second full geometry baseline.
        host.run("(setq result (EL:Put 'snapshot (list (cons 'signature formal)) result))")
        self.assertTrue(truth(host.run("(EL:SaveDraft result nil nil 'cap300)")))
        host.run('(setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(host.run("(EL:Get 'draft-source-signature reopened)"), host.run("'formal-source"))
        self.assertEqual(host.run("(EL:Get 'source-signature reopened)"), host.lookup('FORMAL'))

    def test_generation_persists_members_and_clears_draft_source(self):
        fixture = incremental.IncrementalTests()
        fixture.setUp()
        fixture.prime_current_record()
        host = fixture.h
        host.run("(setq result (EL:Put 'snapshot (EL:CircuitSnapshot '((drawing . \"fixture\") (wires)) \"source\") result))")
        self.assertTrue(truth(host.run("(EL:SaveDraft result nil nil 'cap300)")))
        original_getvar=host.builtins['GETVAR']
        host.builtins.update({
            'GETVAR':lambda key:1 if key=='TILEMODE' else 2 if key=='CVPORT' else original_getvar(key),
            'GETPOINT':lambda *args:[100.,200.,0.],
            'TRANS':lambda point,*args:point,
            'VLA-REGEN':lambda *args:None,
            'EL:SHOWDIAGRAM':lambda *args:True,
            'EL:ALLOWEDVALUES':lambda entity:['CAP300','CAP600','CAP1000',
                'NORMAL','GROUND','RESERVE'],
        })
        self.assertTrue(truth(host.run("(EL:SyncDiagram result nil nil 'cap300 T T)")))
        host.run('(setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertEqual(host.run("(EL:Get 'panel-circuits reopened)"), host.run("(EL:Get 'circuits result)"))
        self.assertEqual(host.run("(EL:Get 'source-signature reopened)"), host.run("(EL:Get 'signature (EL:Get 'snapshot result))"))
        self.assertIsNone(host.run("(EL:Get 'draft-source-signature reopened)"))
        self.assertIsNone(host.run("(EL:Get 'draft-circuits reopened)"))
        before = copy.deepcopy(fixture.fixture.entities)
        first=host.run('(EL:Get \'diagram-id reopened)')
        self.assertTrue(truth(host.run("(EL:SyncDiagram result nil nil 'cap300 T T)")))
        second=host.run('(EL:Get \'diagram-id (EL:DiagramForPanel "source" (EL:StoreRead)))')
        self.assertNotEqual(first,second)
        self.assertEqual(fixture.fixture.call('EL:StoreRecord',first),host.lookup('REOPENED'))
        for handle,*_ in fixture.fixture.call('EL:DiagramOutputRefs',host.lookup('REOPENED')):
            self.assertEqual(fixture.fixture.entities[handle],before[handle])

    def test_unchanged_older_record_gets_members_with_one_record_write(self):
        fixture = incremental.IncrementalTests()
        fixture.setUp()
        fixture.prime_current_record()
        host = fixture.h
        host.run('''
          (setq record (vl-remove-if '(lambda (row) (equal (car row) 'panel-circuits)) record))
          (EL:StoreWrite (EL:StorePutDiagram record (EL:StoreRead)))
        ''')
        fixture.native.clear()
        fixture.master.clear()
        fixture.fixture.undo.clear()
        self.assertTrue(truth(fixture.sync()))
        self.assertEqual(fixture.native, [])
        self.assertEqual(len(fixture.master), 1)
        self.assertEqual(host.run('(EL:Get \'panel-circuits (EL:DiagramForPanel "source" (EL:StoreRead)))'),
                         host.run("(EL:Get 'circuits result)"))
        self.assertEqual(host.run('(EL:Get \'panel-output-handle (EL:DiagramForPanel "source" (EL:StoreRead)))'), 'panel')


if __name__ == '__main__':
    unittest.main()
