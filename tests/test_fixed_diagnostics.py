"""Fixed entry, real panel fill and missing system-variable regressions. Date: 2026-10-13.

Finite CAD/DCL adapters only; native AutoCAD acceptance remains pending.
"""
import unittest
from pathlib import Path
from autolisp_host import Pair, Symbol, truth
import test_panel as panel
import test_diagnostics as diagnostics
import test_cad_adapter as adapter


class FixedDiagnosticTests(unittest.TestCase):
    call = panel.PanelTests.call
    get = panel.PanelTests.get
    line = panel.PanelTests.line
    block = panel.PanelTests.block
    plan = panel.PanelTests.plan
    logging = diagnostics.DiagnosticTests.logging

    def setUp(self):
        panel.PanelTests.setUp(self)
        self.logging()
        for name in ('generation', 'fixed', 'diagram-update', 'diagram-commands', 'insert-circuit'):
            self.h.load_definitions(adapter.ROOT / 'src' / f'{name}.lsp')
        self.plan()
        self.h.builtins['EL:DLSNAPSHOT'] = lambda: self.h.run(
            "'((root . \"library-fixture/\") (catalog (schema . EL_DEVICE_LIBRARY_V1) (library-id . \"LIB-FIXTURE\") (revision . 0) (next-id . 1) (devices)) (index) (present))")
        self.tiles, self.dialogs, self.writes, self.variables = {}, [], [], []
        # Enter on the first existing-diagram prompt selects new generation.
        picks = iter([['panel', [0., 0., 0.]], None, ['w1', [1., 0., 0.]], None])

        def getvar(key):
            self.variables.append(key)
            return {'FINGERPRINTGUID': 'guid', 'CDATE': 20261009.12,
                    'MILLISECS': 100}.get(key)  # Unknown variable => nil, including HANDSEED.

        def tile(key, value):
            if not isinstance(value, str):
                raise TypeError('bad argument type: stringp nil')
            self.tiles[key] = value

        def strcat(*values):
            if any(type(value) is not str for value in values):
                raise TypeError('bad argument type: stringp nil')
            return ''.join(values)

        self.h.builtins.update({
            'GETVAR': getvar, 'EL:ENSUREROOT': lambda: True,
            'STRCAT': strcat, 'FINDFILE': lambda path: path if Path(path).exists() else None,
            'EL:PICKMODEL': lambda *args: next(picks),
            'EL:LOADCONFIG': lambda: self.cfg,
            # Date: 2026-10-12. Explicit fixture preset avoids machine registry.
            'EL:PRESETLOAD': lambda: self.cfg,
            'CHR': chr,
            'HANDENT': lambda e: e if e in self.entities else None,
            'EL:REVIEWFIXEDEXITS': lambda result, record: result,
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
            'EL:CLEARGAPPREVIEW': lambda: None,
            'EL:DRAWTRANSIENT': lambda *args: None,
            'EL:HIGHLIGHTPICK': lambda *args: None,
            'LOAD_DIALOG': lambda path: 1,
            'NEW_DIALOG': lambda name, number: self.dialogs.append(name) or True,
            'UNLOAD_DIALOG': lambda number: None,
            'SET_TILE': tile, 'MODE_TILE': lambda *args: None,
            'START_LIST': lambda *args: None, 'ADD_LIST': lambda *args: None,
            'END_LIST': lambda: None, 'ACTION_TILE': lambda *args: None,
            'EL:THUMBCAPTURE': lambda block: None,
            'DIMX_TILE': lambda key: 160, 'DIMY_TILE': lambda key: 60,
            'START_IMAGE': lambda key: None, 'END_IMAGE': lambda: None,
            'FILL_IMAGE': lambda *args: None, 'VECTOR_IMAGE': lambda *args: None,
            'START_DIALOG': lambda: 0,  # Cancel must preserve all persistent data.
            'EL:STOREWRITE': lambda value: self.writes.append(value),
            'EL:WRITEDATA': lambda *args: self.writes.append(args),
        })




    def test_empty_device_rows_do_not_call_native_sort(self):
        self.h.builtins['VL-SORT'] = lambda *args: self.fail('empty rows sorted')
        self.assertFalse(truth(self.call('EL:SimpleRows', None, None)))

    def test_new_record_avoids_existing_ids_and_retains_existing_record(self):
        first = self.call('EL:NewRecord', 'panel', self.call('EL:StoreInitial'))
        store = self.call('EL:StorePutDiagram', first, self.call('EL:StoreInitial'))
        second = self.call('EL:NewRecord', 'panel', store)
        self.assertNotEqual(self.get('diagram-id', first), self.get('diagram-id', second))
        self.assertEqual(self.call('EL:DiagramForPanel', 'panel', store), first)
        self.assertEqual(self.writes, [])







if __name__ == '__main__':
    unittest.main()
