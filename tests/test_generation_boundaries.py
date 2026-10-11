"""Source/template guards across callbacks and native placement. Date: 2026-10-11."""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
import test_freshness_reuse as freshness
import test_cckk_panel_command as native
import test_diagram_store as db


class FreshCallbackBoundaryTests(unittest.TestCase):
    setUp = freshness.FreshnessReuseTests.setUp
    call = freshness.FreshnessReuseTests.call
    result = freshness.FreshnessReuseTests.result

    def prepare_callback(self):
        result = self.result()
        self.h.frames[0]['*EL:FRESHSCOPEENABLED*'] = True
        inside = []

        def change(*args):
            inside.append(truth(self.call('EL:FreshResult', result, self.f.cfg)))
            self.f.line('w1', [1., 0., 0.], [8., 0., 0.], 'W')
            return True

        return result, inside, change

    def test_input_callback_sample_cannot_survive_its_later_source_edit(self):
        result, inside, change = self.prepare_callback()
        self.h.builtins['TEST:INPUT'] = change
        self.call('EL:PerfInput', Symbol('TEST:INPUT'), [])
        self.assertEqual(inside, [True])
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))

    def test_native_placement_callback_sample_is_invalidated_on_return(self):
        for stage in ('PLACEMENT_INPUT', 'PANEL_DIALOG'):
            with self.subTest(stage=stage):
                self.setUp()
                result, inside, change = self.prepare_callback()
                self.h.builtins['TEST:PLACE'] = change
                self.call('EL:PerfCall', stage, Symbol('TEST:PLACE'), [])
                self.assertEqual(inside, [True])
                self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))

    def test_native_write_callback_sample_is_invalidated_on_return(self):
        result, inside, change = self.prepare_callback()
        self.h.builtins['TEST:WRITE'] = change
        self.call('EL:PerfWrite', Symbol('TEST:WRITE'), [])
        self.assertEqual(inside, [True])
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))

    def test_template_probe_cleanup_invalidates_a_sample_taken_by_probe(self):
        result = self.result()
        self.h.frames[0]['*EL:FRESHSCOPEENABLED*'] = True
        self.h.load_definitions(db.ROOT / 'src' / 'fixed.lsp')
        sampled = []
        deleted = []

        def probe(entity):
            sampled.append(truth(self.call('EL:FreshResult', result, self.f.cfg)))
            return True

        def cleanup(entity):
            deleted.append(entity)
            self.f.line('w1', [1., 0., 0.], [8., 0., 0.], 'W')

        table = self.h.builtins['TBLSEARCH']
        self.h.builtins.update({
            'EL:FINDFIXEDBLOCK': lambda name: None,
            'TBLSEARCH': lambda kind, name: ([Pair(2, name)] if name == 'probe-definition'
                                            else table(kind, name)),
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda _: 'doc',
            'VLA-GET-MODELSPACE': lambda _: 'space',
            'VLAX-3D-POINT': lambda point: point,
            'VLA-INSERTBLOCK': lambda *args: 'probe',
            'VLAX-VLA-OBJECT->ENAME': lambda entity: entity,
            'VLA-DELETE': cleanup,
            'TEST:PROBE': probe,
        })
        self.assertTrue(truth(self.call('EL:WithFixedBlock', 'probe-definition', Symbol('TEST:PROBE'), [])))
        self.assertEqual(sampled, [True])
        self.assertEqual(deleted, ['probe'])
        self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))

    def test_regen_and_zoom_callbacks_cannot_leave_reusable_source_samples(self):
        for phase in ('regen', 'zoom'):
            with self.subTest(phase=phase):
                self.setUp()
                result, inside, change = self.prepare_callback()
                getvar = self.h.builtins['GETVAR']
                self.h.builtins.update({
                    'GETVAR': lambda name: {'TILEMODE': 1, 'CVPORT': 2}.get(name, getvar(name)),
                    'VLAX-GET-ACAD-OBJECT': lambda: 'app',
                    'VLA-GET-ACTIVEDOCUMENT': lambda _: 'doc',
                    'EL:DIAGRAMVIEWBOUNDS': lambda *args: [[0., 0., 0.], [1., 1., 0.]],
                    'VLA-REGEN': change if phase == 'regen' else lambda *args: None,
                    'EL:SIMPLEZOOM': change if phase == 'zoom' else lambda *args: True,
                })
                self.assertTrue(truth(self.call('EL:ShowDiagramBody', [], [])))
                self.assertEqual(inside, [True])
                self.assertFalse(truth(self.call('EL:FreshResult', result, self.f.cfg)))


class NativePlacementBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.f = native.PanelCommandTests()
        self.f.setUp()
        self.h = self.f.h

    def test_source_change_during_mouse_placement_rolls_back_before_rows(self):
        source = {'version': 1}
        checked = []
        original_command = self.h.builtins['COMMAND']

        def command(*args):
            original_command(*args)
            if args[-1] == 'pause':
                source['version'] = 2

        def current(result, cfg):
            checked.append(source['version'])
            return source['version'] == 1

        self.h.builtins.update({'COMMAND': command, 'EL:FRESHRESULT': current})
        self.assertFalse(truth(self.f.invoke()))
        self.assertIn(2, checked)
        self.assertEqual(len(self.f.commands), 1)
        self.assertFalse(any(name.startswith('native-') for name in self.f.entities))
        saved = self.h.run('(EL:DiagramForPanel "source" (EL:StoreRead))')
        self.assertFalse(truth(self.f.get('panel-output-handle', saved)))

    def test_actual_template_definition_change_during_placement_rolls_back(self):
        definitions = {
            'dfgjhdrtyjtfgj4SADFG3': ['panel-definition', 1],
            'fghjftyuk': ['circuit-definition', 1],
        }
        self.h.builtins.pop('EL:TEMPLATERUNTIMEVALID')
        self.h.builtins.update({
            'EL:DEFINITIONDATA': lambda name, stack: copy.deepcopy(definitions[name]),
            'SSGET': lambda *args: list(self.f.entities),
            'SSLENGTH': len,
            'SSNAME': lambda ss, index: ss[index],
        })
        self.h.run("""(foreach key '(panel circuit)
            (setq definition (EL:Get key template))
            (setq template (EL:Put key (EL:Put 'definition
                (EL:Signature (EL:DefinitionData (EL:Get 'name definition) nil)) definition) template)))
            (setq cfg (EL:Put 'template template cfg))
            (setq record (EL:Put 'template template record))
            (EL:StoreWrite (EL:StorePutDiagram record store))""")
        self.assertTrue(truth(self.f.call('EL:TemplateRuntimeValid', self.h.lookup('TEMPLATE'), self.h.lookup('CFG'))))
        original_command = self.h.builtins['COMMAND']

        def command(*args):
            original_command(*args)
            if args[-1] == 'pause':
                definitions['fghjftyuk'][1] = 2

        self.h.builtins['COMMAND'] = command
        self.assertFalse(truth(self.f.invoke()))
        self.assertEqual(len(self.f.commands), 1)
        self.assertFalse(any(name.startswith('native-') for name in self.f.entities))


if __name__ == '__main__':
    unittest.main()
