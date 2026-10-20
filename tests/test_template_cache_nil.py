"""Cold template caches through real capture and panel callbacks.

Date: 2026-10-21. Status: focused adapter regression; native CAD acceptance pending.
The host must reject NTH(nil); COM, selection sets and DCL have finite adapters.
"""
import copy
import unittest

from autolisp_host import Pair, Symbol, truth
import test_panel_library_toggle as layouts
import test_template_choices as choices


class TemplateCacheNilTests(unittest.TestCase):
    fixture = layouts.PanelLibraryToggleTests.fixture

    def native_templates(self, host=None, instances=True):
        f = choices.TemplateChoiceTests()
        f.setUp()
        self.h = host or f.h
        self.cfg = f.cfg
        self.messages, self.scans, self.dynamic_reads = [], [], []
        self.inserted, self.deleted = [], []
        self.names = {'tpl-panel': f.names['panel'], 'tpl-circuit': f.names['circuit']}
        self.properties = {'tpl-panel': f.properties['panel'], 'tpl-circuit': f.properties['circuit']}
        self.entities = {
            e: [Pair(0, 'INSERT'), Pair(5, e), Pair(2, name)]
            for e, name in self.names.items() if instances
        }
        definitions = {name: 'def-' + e for e, name in self.names.items()}
        for e in definitions.values():
            self.entities[e] = [Pair(0, 'LINE'), Pair(10, [0., 0., 0.]), Pair(11, [10., 0., 0.])]
        original_entget = self.h.builtins.get('ENTGET', lambda e: None)
        original_entnext = self.h.builtins.get('ENTNEXT', lambda e: None)
        original_table = self.h.builtins.get('TBLSEARCH', lambda *args: None)
        original_handent = self.h.builtins.get('HANDENT', lambda e: None)
        original_name = self.h.builtins.get('EL:EFFECTIVENAME', lambda e: None)
        required_styles = {'_TEL_DIM', 'ICDA-STYLE1'}
        self.missing_styles = set()

        def table(kind, name):
            if kind == 'BLOCK' and name in definitions:
                return [Pair(2, name), Pair(-2, definitions[name])]
            if kind == 'STYLE' and name in required_styles:
                return None if name in self.missing_styles else [Pair(2, name), Pair(40, 0.)]
            if kind == 'LAYER':
                return None  # Output layers can be created later; none is locked here.
            return original_table(kind, name)

        def scan(*args):
            self.scans.append(args)
            return [e for e in self.entities if e in self.names]

        def dynamic(e, method):
            self.dynamic_reads.append(e)
            return self.properties[e]

        def insert(space, point, name, *args):
            e = 'probe-' + str(len(self.inserted) + 1)
            source = next(e for e, value in self.names.items() if value == name)
            self.inserted.append(e)
            self.names[e], self.properties[e] = name, self.properties[source]
            self.entities[e] = [Pair(0, 'INSERT'), Pair(5, e), Pair(2, name)]
            return e

        def delete(e):
            self.deleted.append(e)
            self.entities.pop(e)

        # Use the actual definition reader; only native calls are adapted.
        self.h.builtins.pop('EL:DEFINITIONDATA', None)
        for key in ('TYPE', 'VLAX-VARIANT-VALUE', 'VLAX-SAFEARRAY->LIST', 'VLAX-GET-PROPERTY',
                    'VLAX-ENAME->VLA-OBJECT', 'VLA-GET-ISDYNAMICBLOCK', 'VLA-GET-READONLY',
                    'VLA-GET-PROPERTYNAME', 'VLA-GET-VALUE', 'VLAX-VARIANT-TYPE',
                    'VLAX-MAKE-VARIANT', 'VLA-PUT-VALUE'):
            self.h.builtins[key] = f.h.builtins[key]
        self.h.frames[0].update({':VLAX-TRUE': -1, ':VLAX-FALSE': 0})
        self.h.builtins.update({
            'NAMEDOBJDICT': lambda: 'nil-cache-drawing',
            'TBLSEARCH': table,
            'ENTGET': lambda e, *apps: copy.deepcopy(self.entities[e]) if e in self.entities else original_entget(e, *apps),
            'ENTNEXT': lambda e: None if e in self.entities else original_entnext(e),
            'HANDENT': lambda e: e if e in self.entities else original_handent(e),
            'EL:EFFECTIVENAME': lambda e: self.names.get(e) or original_name(e),
            'SSGET': scan, 'SSLENGTH': len, 'SSNAME': lambda ss, index: ss[index],
            'VLAX-INVOKE': dynamic,
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda app: 'doc',
            'VLA-GET-MODELSPACE': lambda doc: 'space',
            'VLAX-3D-POINT': lambda point: point,
            'VLA-INSERTBLOCK': insert,
            'VLAX-VLA-OBJECT->ENAME': lambda e: e,
            'VLA-DELETE': delete,
            'PRINC': lambda value='': self.messages.append(str(value)),
        })
        for key in ('*EL:FIXEDSAMPLES*', '*EL:TEMPLATEDYNAMICMEMO*', '*EL:TEMPLATELIVEPROBES*'):
            self.h.set(key, None)
        return f

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def panel_fixture(self):
        f, callbacks, _, _ = self.fixture(False)
        self.addCleanup(f.doCleanups)
        self.native_templates(f.h)
        self.alerts = []
        f.h.builtins.update({'ALERT': self.alerts.append,
                             'EL:DLPANELSUBMISSIONREADY': lambda: True})
        return f, callbacks

    def snapshot(self, f):
        return copy.deepcopy([f.h.lookup(key) for key in (
            '*EL:PANELDRAFT*', '*EL:PANELPOWERS*', '*EL:PANELCAPACITY*')])

    def test_empty_dynamic_memo_performs_fresh_check_then_reuses_within_scope(self):
        self.native_templates()
        template = self.call('EL:CaptureFixedTemplate', self.cfg)
        self.assertTrue(truth(template))
        self.dynamic_reads.clear()
        self.h.frames[0].update({'TEMPLATE': template, 'CFG': self.cfg})
        self.h.run("""(defun test:validate-cold ()
            (and (not *EL:TemplateDynamicMemo*)
              (EL:TemplateRuntimeValid template cfg)
              (= 2 (length *EL:TemplateDynamicMemo*))
              (EL:TemplateRuntimeValid template cfg)))""")
        self.assertTrue(truth(self.call('EL:WithTemplateScope', Symbol('TEST:VALIDATE-COLD'), None)))
        self.assertEqual(self.dynamic_reads, ['tpl-panel', 'tpl-circuit'])
        self.assertIsNone(self.h.lookup('*EL:TEMPLATEDYNAMICMEMO*'))

    def test_empty_live_probe_cache_falls_back_to_scan_then_existing_handle(self):
        self.native_templates()
        name = self.names['tpl-panel']
        self.assertEqual(self.call('EL:FindFixedBlock', name), 'tpl-panel')
        self.assertEqual(self.call('EL:FindFixedBlock', name), 'tpl-panel')
        self.assertEqual(len(self.scans), 1)
        self.assertEqual(self.inserted, [])

    def test_definition_only_capture_uses_two_live_probes_and_cleans_both(self):
        self.native_templates(instances=False)
        template = self.call('EL:CaptureFixedTemplate', self.cfg)
        self.assertTrue(truth(template), ''.join(self.messages))
        self.assertEqual(len(self.inserted), 2)
        self.assertEqual(self.deleted, list(reversed(self.inserted)))
        self.assertTrue(all(e not in self.entities for e in self.inserted))
        for kind in ('panel', 'circuit'):
            self.assertIsNone(self.call('EL:Get', Symbol('SOURCE-HANDLE'),
                                       self.call('EL:Get', Symbol(kind.upper()), template)))
        self.assertIsNone(self.h.lookup('*EL:TEMPLATELIVEPROBES*'))
        self.assertIsNone(self.h.lookup('*EL:TEMPLATEDYNAMICMEMO*'))

    def test_real_generate_callback_prepares_cold_template_and_returns_generate_request(self):
        f, callbacks = self.panel_fixture()
        before = []

        def generate():
            f.call('EL:PanelCapacity', 'p_600')
            before.append(self.snapshot(f))
            f.invoke_action(callbacks, 'p_generate')
            self.assertEqual(f.closed, 4)

        f.actions = [generate]
        result = f.dialog()
        self.assertTrue(truth(f.get('generate', result)), ''.join(self.messages))
        self.assertEqual(len(f.dialogs), 1, 'successful preparation must not flash back to the panel')
        self.assertEqual([f.get('result', result), f.get('powers', result), f.get('capacity', result)], before[0])
        self.assertTrue(truth(f.call('EL:TemplateRuntimeValid',
                                    f.get('template', f.get('config', result)), f.cfg)))
        self.assertEqual(self.alerts, [])

    def test_accepted_cold_template_reaches_save_and_generation_dispatch(self):
        f, callbacks = self.panel_fixture()
        dispatched, events = [], []
        resume = None
        for key, value in (('result', f.result), ('config', f.cfg),
                           ('powers', f.powers), ('capacity', Symbol('CAP600'))):
            resume = f.call('EL:Put', Symbol(key.upper()), value, resume)
        f.h.set('*EL:DLRESUME*', resume)

        def save(result, cfg, powers, capacity):
            self.assertTrue(truth(f.call('EL:TemplateRuntimeValid', f.get('template', cfg), cfg)))
            dispatched.append(('save', copy.deepcopy([result, cfg, powers, capacity])))
            return True

        def generate(result, cfg, powers, capacity):
            self.assertEqual(len(dispatched), 1, 'generation must follow the input save boundary')
            self.assertTrue(truth(f.call('EL:TemplateRuntimeValid', f.get('template', cfg), cfg)))
            dispatched.append(('generate', copy.deepcopy([result, cfg, powers, capacity])))
            return True

        f.h.builtins.update({'EL:SAVEDRAFT': save, 'EL:INVOKECCKK2': generate,
                             'EL:LOGEVENT': lambda *args: events.append(args)})

        def click_generate():
            f.invoke_action(callbacks, 'p_generate')
            self.assertEqual(f.closed, 4)

        f.actions = [click_generate]
        f.call('EL:EditPanelOnce', f.result, f.cfg)
        self.assertEqual([kind for kind, _ in dispatched], ['save', 'generate'],
                         ''.join(self.messages) + repr(events))
        self.assertEqual(dispatched[0][1], dispatched[1][1])
        self.assertEqual(len(f.dialogs), 1)
        self.assertEqual(self.alerts, [])

    def test_missing_style_or_incompatible_dynamic_property_keeps_panel_inputs(self):
        for failure in ('style', 'property'):
            with self.subTest(failure=failure):
                f, callbacks = self.panel_fixture()
                if failure == 'style':
                    self.missing_styles.add('_TEL_DIM')
                else:
                    self.properties['tpl-panel'][0]['readonly'] = -1
                before = []

                def generate():
                    f.call('EL:PanelCapacity', 'p_1000')
                    before.append(self.snapshot(f))
                    f.invoke_action(callbacks, 'p_generate')
                    self.assertEqual(f.closed, 4)

                def returned():
                    self.assertEqual(self.snapshot(f), before[0])
                    self.assertFalse(truth(f.h.lookup('*EL:PANELTEMPLATEREADY*')))
                    f.invoke_action(callbacks, 'cancel')

                f.actions = [generate, returned]
                self.assertIsNone(f.dialog())
                self.assertEqual(len(f.dialogs), 2)
                self.assertEqual(self.alerts, [])
                self.assertIn('当前识别结果、功率和容量已保留', ''.join(self.messages))
                self.assertNotIn('consp nil', ''.join(self.messages))

    def test_cancelled_real_state_mapping_keeps_panel_inputs_and_does_not_generate(self):
        f, callbacks = self.panel_fixture()
        template = choices.TemplateChoiceTests()
        self.properties['tpl-panel'] = [template.prop('容量状态', ['小容量', '中容量', '大容量'])]
        self.h.builtins['GETINT'] = lambda prompt: None
        before = []

        def generate():
            f.call('EL:PanelCapacity', 'p_600')
            before.append(self.snapshot(f))
            f.invoke_action(callbacks, 'p_generate')
            self.assertEqual(f.closed, 4)

        def returned():
            self.assertEqual(self.snapshot(f), before[0])
            self.assertFalse(truth(f.h.lookup('*EL:PANELTEMPLATEREADY*')))
            f.invoke_action(callbacks, 'cancel')

        f.actions = [generate, returned]
        self.assertIsNone(f.dialog())
        self.assertEqual(len(f.dialogs), 2)
        self.assertIn('已取消本次模板设置', ''.join(self.messages))
        self.assertEqual(self.alerts, [])


if __name__ == '__main__':
    unittest.main()
