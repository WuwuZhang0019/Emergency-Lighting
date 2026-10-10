"""Temporary circuit display copies and recovery. Date: 2026-10-10."""
import unittest
from autolisp_host import Symbol
from test_fixed_exit_preview import FixedExitPreviewTests


class CircuitColorTests(unittest.TestCase):
    call = FixedExitPreviewTests.call
    get = FixedExitPreviewTests.get
    line = FixedExitPreviewTests.line
    block = FixedExitPreviewTests.block
    plan = FixedExitPreviewTests.plan
    logging = FixedExitPreviewTests.logging
    redraw = FixedExitPreviewTests.redraw
    draw = FixedExitPreviewTests.draw
    zoom = FixedExitPreviewTests.zoom

    def setUp(self):
        FixedExitPreviewTests.setUp(self)
        self.objects = {k: {'visible': -1, 'color': 256, 'kind': 'AcDbLine'} for k in self.entities}
        self.objects['a']['kind'] = 'AcDbBlockReference'
        self.created = []
        self.fail_color = False
        self.h.frames[0].update({':VLAX-TRUE': -1, ':VLAX-FALSE': 0})
        def copy(obj):
            key = f'copy{len(self.created)}'
            self.created.append(key)
            self.objects[key] = dict(self.objects[obj])
            return key
        def explode(obj):
            children = [copy(obj), copy(obj)]
            for child in children:
                self.objects[child]['kind'] = 'AcDbLine'
            return children
        def color(obj, value):
            if self.fail_color and len(self.created) >= 3:
                raise RuntimeError('injected color failure')
            self.objects[obj]['color'] = value
        self.h.builtins.update({
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda app: 'doc',
            'VLA-STARTUNDOMARK': lambda doc: None,
            'VLA-ENDUNDOMARK': lambda doc: None,
            'VLAX-ENAME->VLA-OBJECT': lambda obj: obj,
            'VLA-COPY': copy, 'VLA-EXPLODE': explode,
            'VLAX-VARIANT-VALUE': lambda value: value,
            'VLAX-SAFEARRAY->LIST': lambda value: value,
            'VLA-GET-OBJECTNAME': lambda obj: self.objects[obj]['kind'],
            'VLA-PUT-LAYER': lambda *args: None,
            'VLA-PUT-COLOR': color,
            'VLA-GET-VISIBLE': lambda obj: self.objects[obj]['visible'],
            'VLA-PUT-VISIBLE': lambda obj, value: self.objects[obj].__setitem__('visible', value),
            'VLA-DELETE': lambda obj: self.objects.pop(obj),
        })
        self.result = self.h.run("'((circuits ((wires \"w1\" \"w2\") (devices \"a\")) ((devices \"b\"))))")

    def assert_clean(self):
        self.assertTrue(all(k not in self.objects for k in self.created))
        self.assertTrue(all(o['visible'] == -1 and o['color'] == 256 for o in self.objects.values()))
        self.assertFalse(self.h.lookup('*EL:COLORPREVIEWCOPIES*'))
        self.assertFalse(self.h.lookup('*EL:COLORPREVIEWSOURCES*'))

    def test_same_circuit_wires_and_exploded_device_share_color(self):
        paused = []
        def pause(*args):
            paused.append(True)
            copies = [self.objects[k] for k in self.created if k in self.objects]
            self.assertEqual([o['color'] for o in copies], [1, 1, 1, 1, 3])
            self.assertTrue(all(self.objects[k]['visible'] == 0 for k in ('w1', 'w2', 'a', 'b')))
            self.assertTrue(all(self.objects[k]['color'] == 256 for k in ('w1', 'w2', 'a', 'b')))
            return ''
        self.h.builtins['GETSTRING'] = pause
        self.call('EL:AllCircuitColorPreview', self.result)
        self.assertEqual(paused, [True])
        self.assert_clean()

    def test_escape_restores_sources_and_removes_all_copies(self):
        def cancel(*args):
            raise RuntimeError('Function cancelled')
        self.h.builtins['GETSTRING'] = cancel
        self.call('EL:AllCircuitColorPreview', self.result)
        self.assert_clean()

    def test_partial_explosion_failure_removes_unprocessed_children(self):
        self.fail_color = True
        self.call('EL:AllCircuitColorPreview', self.result)
        self.assert_clean()
        self.assertIn('injected color failure', ''.join(self.messages))

    def test_shared_entity_is_rejected_before_copying(self):
        result = self.h.run("'((circuits ((wires \"w1\")) ((wires \"w1\"))))")
        self.call('EL:AllCircuitColorPreview', result)
        self.assertEqual(self.created, [])
        self.assertIn('多回路共用对象', ''.join(self.messages))

    def test_cleanup_failure_keeps_retry_registry(self):
        self.call('EL:ColorPreviewEntity', 'w1', 1)
        delete = self.h.builtins['VLA-DELETE']
        def fail(obj):
            raise RuntimeError('locked')
        self.h.builtins['VLA-DELETE'] = fail
        self.assertFalse(self.call('EL:ColorPreviewCleanup'))
        self.assertTrue(self.h.lookup('*EL:COLORPREVIEWCOPIES*'))
        self.h.builtins['VLA-DELETE'] = delete
        self.call('EL:ColorPreviewCleanup')
        self.assert_clean()

    def test_palette_is_distinct(self):
        self.assertEqual(len({self.call('EL:CircuitColor', i) for i in range(24)}), 24)

    def test_virtual_trunk_piece_uses_only_split_geometry_and_restores_source(self):
        lines = []
        def add_line(space, a, b):
            key = f'piece{len(lines)}'
            lines.append((a, b))
            self.created.append(key)
            self.objects[key] = {'visible': -1, 'color': 256, 'kind': 'AcDbLine'}
            return key
        self.h.builtins.update({'VLA-GET-MODELSPACE': lambda _: 'space',
                               'VLAX-3D-POINT': lambda p: p, 'VLA-ADDLINE': add_line})
        wire = self.h.run("'((source-wire . \"w1\") (segments ((5.0 0.0 0.0) (9.0 0.0 0.0))))")
        self.call('EL:ColorPreviewWire', wire, 3)
        self.assertEqual(lines, [([5., 0., 0.], [9., 0., 0.])])
        self.assertEqual(self.objects['w1']['visible'], 0)
        self.assertEqual(self.objects['piece0']['color'], 3)
        self.call('EL:ColorPreviewCleanup')
        self.assert_clean()


if __name__ == '__main__':
    unittest.main()
