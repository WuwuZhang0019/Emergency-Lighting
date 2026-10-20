"""Date: 2026-10-21. Status: current. Scoped template proof and probe boundaries.

Finite native-shaped adapters; call counts are not native AutoCAD timing.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
import test_template_choices as choices


class TemplateReuseTests(unittest.TestCase):
    def setUp(self):
        self.f = choices.TemplateChoiceTests()
        self.f.setUp()
        self.h = self.f.h
        self.owner = 'dwg-a'
        self.scans, self.definition_reads, self.dynamic_reads = [], [], []
        self.clock = 0
        self.entities = {e: [Pair(0, 'INSERT'), Pair(5, e), Pair(2, name)]
                         for e, name in self.f.names.items()}
        self.definitions = {name: 'definition-' + e for e, name in self.f.names.items()}
        self.next_entities = {}
        for name, e in self.definitions.items():
            self.entities[e] = [Pair(0, 'LINE'), Pair(10, [0., 0., 0.]),
                                Pair(11, [10., 0., 0.])]
            # A fixed diagonal keeps the overall extents unchanged when the inner line moves.
            self.entities[e + '-bounds'] = [Pair(0, 'LINE'), Pair(10, [0., 0., 0.]),
                                            Pair(11, [10., 10., 0.])]
            self.next_entities[e] = e + '-bounds'
        table = self.h.builtins['TBLSEARCH']
        self.h.functions[Symbol('TEST:DEFINITIONDATA')] = self.h.functions[Symbol('EL:DEFINITIONDATA')]
        self.h.builtins.update({
            'NAMEDOBJDICT': lambda: self.owner,
            'TBLSEARCH': lambda kind, name: ([Pair(2, name), Pair(-2, self.definitions[name])]
                if kind == 'BLOCK' and name in self.definitions else table(kind, name)),
            'ENTGET': lambda e: copy.deepcopy(self.entities.get(e)),
            'ENTNEXT': lambda e: self.next_entities.get(e),
            'HANDENT': lambda e: e if e in self.entities else None,
            'SSGET': self.scan,
            'EL:DEFINITIONDATA': self.definition,
            'VLAX-INVOKE': self.dynamic,
            'GETVAR': self.getvar,
        })
        self.template = self.call('EL:CaptureFixedTemplate', self.f.cfg)
        self.assertTrue(truth(self.template))
        self.h.frames[0].update({'TEMPLATE': self.template, 'CFG': self.f.cfg})
        self.scans.clear()
        self.definition_reads.clear()
        self.dynamic_reads.clear()
        self.call('EL:PerfStart', 'ELSTAT')

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def getvar(self, name):
        if name == 'MILLISECS':
            self.clock += 1
            return self.clock
        return 20261021.123456 if name == 'CDATE' else None

    def scan(self, *args):
        self.scans.append(args)
        return [e for e, rows in self.entities.items()
                if any(isinstance(row, Pair) and row.car == 0 and row.cdr == 'INSERT' for row in rows)]

    def definition(self, name, stack):
        self.definition_reads.append(name)
        return self.call('TEST:DefinitionData', name, stack)

    def dynamic(self, entity, method):
        self.dynamic_reads.append(entity)
        return self.f.properties[entity]

    def metric(self, key):
        return self.call('EL:Get', key, self.h.lookup('*EL:PERFMETRICS*')) or 0

    def scoped(self, body):
        return self.h.run('(defun test:scope () ' + body + ') (EL:WithTemplateScope \'test:scope nil)')

    def test_same_scope_reuses_signatures_and_dynamic_facts_after_exact_source_read(self):
        answer = self.scoped('''(and (EL:TemplateRuntimeValid template cfg)
            (EL:WithTemplateScope 'EL:TemplateRuntimeValid (list template cfg))
            (EL:TemplateRuntimeValid template cfg))''')
        self.assertTrue(truth(answer))
        self.assertEqual(len(self.definition_reads), 2)
        self.assertEqual(len(self.dynamic_reads), 2)
        self.assertEqual(self.metric('template-definition-reuses'), 4)
        self.assertEqual(self.metric('template-dynamic-reuses'), 4)
        self.assertEqual(self.scans, [])
        self.assertGreater(self.metric('template-definition-check-ms'), 0)
        self.assertGreater(self.metric('template-dynamic-check-ms'), 0)

    def test_unscoped_and_new_scopes_do_not_reuse_a_previous_dynamic_success(self):
        for _ in range(2):
            self.assertTrue(truth(self.call('EL:TemplateRuntimeValid', self.template, self.f.cfg)))
        for _ in range(2):
            self.assertTrue(truth(self.scoped('(EL:TemplateRuntimeValid template cfg)')))
        self.assertEqual(len(self.definition_reads), 8)
        self.assertEqual(len(self.dynamic_reads), 8)
        self.assertEqual(self.metric('template-dynamic-reuses'), 0)

    def test_changing_to_another_valid_property_in_same_scope_reads_that_property(self):
        self.f.properties['panel'].append(self.f.prop('alternate', ['0.3kW', '0.6kW', '1kW']))
        answer = self.scoped('''(EL:TemplateRuntimeValid template cfg)
            (setq changed (EL:Put 'panel (EL:Put 'property "alternate" (EL:Get 'panel template)) template))
            (EL:TemplateRuntimeValid changed cfg)''')
        self.assertTrue(truth(answer))
        self.assertEqual(len(self.dynamic_reads), 3)

    def test_same_name_same_bounds_internal_definition_change_is_rejected(self):
        panel_name = self.f.names['panel']
        def change():
            self.entities[self.definitions[panel_name]][-1] = Pair(11, [5., 0., 0.])
        self.h.builtins['TEST:CHANGE'] = change
        self.assertFalse(truth(self.scoped('''(EL:TemplateRuntimeValid template cfg)
            (test:change) (EL:TemplateRuntimeValid template cfg)''')))
        self.assertIn(panel_name, self.h.lookup('*EL:TEMPLATENOTICE*'))
        self.assertEqual(len(self.definition_reads), 3)

    def test_input_and_write_boundaries_recheck_changed_allowed_states(self):
        for wrapper in ('EL:PerfInput', 'EL:PerfWrite'):
            with self.subTest(wrapper=wrapper):
                self.setUp()
                def change():
                    self.f.properties['panel'][0]['allowed'] = ['0.3kW', '0.6kW']
                self.h.builtins['TEST:CHANGE'] = change
                self.assertFalse(truth(self.scoped(f'''(EL:TemplateRuntimeValid template cfg)
                    ({wrapper} 'test:change nil) (EL:TemplateRuntimeValid template cfg)''')))
                self.assertEqual(len(self.dynamic_reads), 4)
                self.assertIn('1kW', self.h.lookup('*EL:TEMPLATENOTICE*'))

    def test_drawing_switch_rechecks_even_when_names_and_handles_match(self):
        self.h.builtins['TEST:SWITCH'] = lambda: setattr(self, 'owner', 'dwg-b')
        self.assertTrue(truth(self.scoped('''(EL:TemplateRuntimeValid template cfg)
            (test:switch) (EL:TemplateRuntimeValid template cfg)''')))
        self.assertEqual(len(self.dynamic_reads), 4)
        self.assertEqual(len(self.definition_reads), 4)

    def test_sample_lookup_uses_known_handle_and_rejects_erased_or_other_actual_definition(self):
        name = self.f.names['panel']
        self.h.set('*EL:FIXEDSAMPLES*', None)
        self.assertEqual(self.call('EL:FindFixedBlock', name), 'panel')
        self.assertEqual(self.call('EL:FindFixedBlock', name), 'panel')
        self.assertEqual(len(self.scans), 1)
        self.entities['panel'][-1] = Pair(2, '*U123')
        self.assertEqual(self.call('EL:FindFixedBlock', name), 'panel')
        self.assertEqual(len(self.scans), 2)
        self.entities.pop('panel')
        self.assertIsNone(self.call('EL:FindFixedBlock', name))
        self.assertEqual(len(self.scans), 3)

    def test_saved_source_handle_avoids_initial_scan(self):
        self.h.set('*EL:FIXEDSAMPLES*', None)
        self.assertTrue(truth(self.scoped('(EL:TemplateRuntimeValid template cfg)')))
        self.assertEqual(self.scans, [])

    def probe_fixture(self, after_delete=None):
        self.deleted, self.inserted = [], []
        self.entities.pop('panel')
        self.entities.pop('circuit')
        def insert(space, point, name, *args):
            e = 'probe-' + str(len(self.inserted) + 1)
            self.inserted.append(e)
            self.entities[e] = [Pair(0, 'INSERT'), Pair(5, e), Pair(2, name)]
            original = next(k for k, value in self.f.names.items() if value == name and not k.startswith('probe-'))
            self.f.names[e] = name
            self.f.properties[e] = self.f.properties[original]
            return e
        def delete(e):
            self.deleted.append(e)
            self.entities.pop(e)
            if after_delete:
                after_delete(e)
        self.h.builtins.update({
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda app: 'doc',
            'VLA-GET-MODELSPACE': lambda doc: 'space',
            'VLAX-3D-POINT': lambda point: point,
            'VLA-INSERTBLOCK': insert,
            'VLAX-VLA-OBJECT->ENAME': lambda e: e,
            'VLA-DELETE': delete,
        })

    def test_capture_and_runtime_validation_share_live_probes_then_clear_dead_handles(self):
        self.probe_fixture()
        template = self.call('EL:CaptureFixedTemplate', self.f.cfg)
        self.assertTrue(truth(template))
        self.assertEqual(len(self.inserted), 2)
        self.assertEqual(self.deleted, list(reversed(self.inserted)))
        self.assertFalse(any(e.startswith('probe-') for e in self.entities))
        for kind in ('panel', 'circuit'):
            self.assertIsNone(self.call('EL:Get', Symbol('SOURCE-HANDLE'),
                                      self.call('EL:Get', Symbol(kind.upper()), template)))
        self.assertIsNone(self.h.lookup('*EL:TEMPLATELIVEPROBES*'))
        self.assertIsNone(self.h.lookup('*EL:TEMPLATEDYNAMICMEMO*'))
        self.assertGreaterEqual(self.metric('template-probe-reuses'), 1)

    def test_cleanup_reactor_allowed_state_change_cannot_reuse_probe_success(self):
        def change(e):
            self.f.properties['panel'][0]['allowed'] = ['0.3kW', '0.6kW']
        self.probe_fixture(change)
        panel = self.call('EL:Get', Symbol('PANEL'), self.template)
        self.h.frames[0]['PANELDEF'] = panel
        self.assertFalse(truth(self.scoped('''(EL:WithFixedBlock (EL:Get 'name paneldef)
            'EL:FixedDefinitionValid (list paneldef))
            (EL:FixedRuntimeDefinitionValid paneldef (car (EL:TemplateDefinitionProof (EL:Get 'name paneldef))))''')))
        self.assertEqual(len(self.inserted), 2)
        self.assertEqual(self.deleted, self.inserted)

    def test_probe_conversion_exception_still_deletes_object(self):
        self.probe_fixture()
        self.h.builtins['VLAX-VLA-OBJECT->ENAME'] = lambda e: (_ for _ in ()).throw(RuntimeError('conversion failed'))
        self.assertIsNone(self.call('EL:CaptureFixedTemplate', self.f.cfg))
        self.assertEqual(len(self.inserted), 1)
        self.assertEqual(self.deleted, self.inserted)
        self.assertIsNone(self.h.lookup('*EL:TEMPLATELIVEPROBES*'))

    def test_drawing_switch_during_probe_rejects_callback_and_still_deletes_object(self):
        self.probe_fixture()
        insert = self.h.builtins['VLA-INSERTBLOCK']
        def switch(*args):
            entity = insert(*args)
            self.owner = 'dwg-b'
            return entity
        self.h.builtins['VLA-INSERTBLOCK'] = switch
        self.assertIsNone(self.call('EL:CaptureFixedTemplate', self.f.cfg))
        self.assertEqual(self.deleted, self.inserted)
        self.assertEqual(self.dynamic_reads, [])
        self.assertIsNone(self.h.lookup('*EL:TEMPLATELIVEPROBES*'))

    def test_unknown_callback_invalidates_prior_success_and_callback_sample(self):
        def change(e):
            self.assertTrue(truth(self.call('EL:TemplateRuntimeValid', self.template, self.f.cfg)))
            self.f.properties['panel'][0]['allowed'] = ['0.3kW', '0.6kW']
            return True
        self.h.builtins['TEST:UNKNOWN'] = change
        self.assertFalse(truth(self.scoped('''(EL:TemplateRuntimeValid template cfg)
            (EL:WithFixedBlock (EL:Get 'name (EL:Get 'panel template)) 'test:unknown nil)
            (EL:TemplateRuntimeValid template cfg)''')))
        self.assertEqual(len(self.dynamic_reads), 6)

    def test_capture_reports_non_dynamic_or_unusable_property_and_cancel(self):
        self.h.builtins['VLA-GET-ISDYNAMICBLOCK'] = lambda e: 0
        self.assertIsNone(self.call('EL:CaptureFixedTemplate', self.f.cfg))
        self.assertIn(self.f.names['panel'], self.h.lookup('*EL:TEMPLATENOTICE*'))
        self.assertIn('不是动态块', self.h.lookup('*EL:TEMPLATENOTICE*'))
        self.h.builtins['VLA-GET-ISDYNAMICBLOCK'] = lambda e: -1
        self.f.properties['panel'] = [self.f.prop('locked', ['a', 'b', 'c'], -1)]
        self.assertIsNone(self.call('EL:CaptureFixedTemplate', self.f.cfg))
        self.assertIn('可写', self.h.lookup('*EL:TEMPLATENOTICE*'))
        self.f.properties['panel'] = [self.f.prop('custom', ['a', 'b', 'c'])]
        self.f.answers = iter([None])
        self.assertIsNone(self.call('EL:CaptureFixedTemplate', self.f.cfg))
        self.assertIn('取消', self.h.lookup('*EL:TEMPLATENOTICE*'))


if __name__ == '__main__':
    unittest.main()
