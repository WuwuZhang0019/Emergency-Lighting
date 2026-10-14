"""Current-panel workflow fixture and storage checks. Date: 2026-10-14. Status: current.

Runs actual command/dialog functions with finite CAD/DCL adapters.
"""
import unittest
import tempfile
from pathlib import Path
import test_device_library as library_backend
import test_fixed_diagnostics as diag
import test_diagram_store as db
from autolisp_host import Pair, Symbol, truth


class PostStatWorkflowTests(unittest.TestCase):
    call = diag.FixedDiagnosticTests.call
    get = diag.FixedDiagnosticTests.get
    line = diag.FixedDiagnosticTests.line
    block = diag.FixedDiagnosticTests.block
    plan = diag.FixedDiagnosticTests.plan
    logging = diag.FixedDiagnosticTests.logging

    def setUp(self):
        diag.FixedDiagnosticTests.setUp(self)
        self.capture_calls, self.actions = [], []
        self.closed = None
        self.h.builtins.update({'GET_TILE': lambda key: self.tiles.get(key, ''),
                               'DONE_DIALOG': self.done,
                               'START_DIALOG': self.start,
                               'WCMATCH': self.monitor_key_match})
        self.result = self.call('EL:RecognizeFixed', self.cfg, 'panel')
        record = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        self.result = self.call('EL:PreparedResult', self.result, record)
        self.powers = self.h.run("'((\"LAMP\" . 5))")
        # Generation workflow fixture has a registered non-ground lamp.
        # Empty/unknown-library generation is covered separately in device recognition checks.
        catalog=self.call('EL:DLCatalogInitial','LIB-WORKFLOW')
        entry=self.call('EL:DLEntryNew',catalog,'LAMP')
        values={'display':'Lamp','watts':5,'ground-confirmed':True,'active':True,'status':Symbol('READY'),
                'asset-revision':1,'block-file':'assets/ELDEV1/1/block.dwg',
                'legend-file':'assets/ELDEV1/1/legend.sld','legend-size':[800,600],'legend-checksum':'sld-123-31'}
        for key,value in values.items():entry=self.call('EL:Put',Symbol(key.upper()),value,entry)
        catalog=self.call('EL:DLUpsert',catalog,entry)
        snapshot=self.h.run("'((root . \"library-fixture/\") (present))")
        snapshot=self.call('EL:Put',Symbol('CATALOG'),catalog,self.call('EL:Put',Symbol('INDEX'),self.call('EL:DLIndex',catalog),snapshot))
        self.h.builtins['EL:DLSNAPSHOT']=lambda:snapshot
        self.h.builtins['EL:DLREMEMBERINPUTS']=lambda *args:True

    def monitor_key_match(self, key, pattern):
        # Native WCMATCH semantics for the monitor's literal-prefix patterns.
        self.assertIn(pattern, ('b_watts*', 'b_ground*', 'b_remove*', 'f_image*'))
        return key.startswith(pattern[:-1])

    def invoke_action(self, callbacks, key):
        # DCL supplies these variables while executing ACTION_TILE code.
        self.h.set('$KEY', key)
        self.h.set('$VALUE', self.tiles.get(key, ''))
        return self.h.run(callbacks[key])

    def done(self, status):
        self.closed = status

    def start(self):
        self.closed = None
        self.actions.pop(0)()
        self.assertIsNotNone(self.closed, 'test action must close the dialog')
        return self.closed

    def confirm(self):
        self.call('EL:PanelCapacity', 'p_600')

    def dialog(self):
        return self.call('EL:PanelDialog', self.result, self.cfg, self.powers, None)









    def unknown_local_power(self):
        snapshot = self.h.run("""'((root . "library-fixture/") (catalog (schema . EL_DEVICE_LIBRARY_V1) (library-id . "LIB-EMPTY") (revision . 0) (next-id . 1) (devices)) (index) (present))""")
        self.h.builtins['EL:DLSNAPSHOT'] = lambda: snapshot
        self.h.set('*EL:DLSESSIONSNAPSHOT*', snapshot)
        prepared = self.call('EL:DLPrepare', self.result, self.powers, snapshot, None)
        self.result = self.get('result', prepared)
        self.result = self.call('EL:DLSetOverride', self.result, 'LAMP', Symbol('WATTS'), 5)
        self.result = self.call('EL:DLSetOverride', self.result, 'LAMP', Symbol('WATTS-SET'), True)

































class SelectionStoreTests(unittest.TestCase):
    def setUp(self):
        db.StoreTests.setUp(self)
        for name in ('config', 'geometry', 'topology', 'statistics', 'generation', 'fixed', 'panel', 'diagram-update', 'diagram-commands'):
            self.h.load_definitions(db.ROOT / 'src' / f'{name}.lsp')
        self.h.builtins['EL:TRANSACTION'] = lambda fn, args: self.h.call(fn, args)
        self.h.builtins['EL:TEMPLATEREADY'] = lambda template, cfg: truth(template)

    def test_draft_confirmation_and_shared_template_roundtrip_through_xrecord(self):
        self.h.run('''(setq cfg '((template (name . "captured"))))
          (setq result '((panel . "source") (engine . fixed) (capacity-source . manual) (can-generate . T)
            (circuits ((id . "R1") (seed (key "wire" outlet)) (circuit-uid . "u1")
              (seed-key "wire" outlet) (is-ground) (ground-source . manual)))))
          (EL:SaveDraft result cfg nil 'cap600)
          (setq result nil cfg nil)
          (setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))''')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"), Symbol('CAP600'))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"), Symbol('MANUAL'))
        self.assertEqual(self.h.run("(EL:Get 'ground-source (car (EL:Get 'draft-circuits reopened)))"), Symbol('MANUAL'))
        self.assertIsNone(self.h.run("(EL:Get 'is-ground (car (EL:Get 'draft-circuits reopened)))"))
        self.assertEqual(self.h.run("(EL:Get 'name (EL:Get 'fixed-template (EL:StoreRead)))"), 'captured')

    def test_missing_capacity_and_ground_use_defaults_without_marking_stale(self):
        self.h.run('''(EL:SaveDraft '((panel . "source") (engine . fixed) (can-generate . T)
          (circuits ((id . "R1") (seed-key "wire" outlet) (ground-source . default)))) nil nil nil)
          (setq reopened (EL:DiagramForPanel "source" (EL:StoreRead)))''')
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity reopened)"),Symbol('CAP300'))
        self.assertEqual(self.h.run("(EL:Get 'draft-capacity-source reopened)"),Symbol('DEFAULT'))
        self.assertNotEqual(self.h.run("(EL:Get 'status reopened)"), Symbol('STALE'))
        self.assertIsNone(self.h.run("(EL:Get 'is-ground (car (EL:Get 'draft-circuits reopened)))"))


if __name__ == '__main__':
    unittest.main()
