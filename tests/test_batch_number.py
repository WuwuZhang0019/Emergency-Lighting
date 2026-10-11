"""Execute standalone HLBH LISP with native boundary adapters. Date: 2026-10-11.

No AutoCAD or Tianzheng is started. These tests verify our input planning,
command protocol, readback and recovery, not the vendor's native interfaces.
"""
import copy
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Host, Pair, Symbol, parse, truth


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/batch-number.lsp'


class NativeAbort(RuntimeError):
    """Model EXIT leaving the native runner instead of producing a result."""


def field(data, code):
    return next((pair.cdr for pair in data if isinstance(pair, Pair) and pair.car == code), None)


class BatchFixture(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        self.h.load_definitions(SOURCE)
        self.variables = {'CMDECHO': 0, 'OSMODE': 551, 'ORTHOMODE': 1,
                          'SNAPMODE': 1, 'DYNMODE': 3, 'DIMSCALE': 1.,
                          'TEXTSIZE': 2.5, 'UNDOCTL': 1, 'CMDACTIVE': 0,
                          'CMDNAMES': '', 'LASTPROMPT': '',
                          'TEMPPREFIX': 'C:/Temp/', 'CDATE': 20261011.12}
        self.original_vars = {key: self.variables[key] for key in
                              ('CMDECHO', 'OSMODE', 'ORTHOMODE', 'SNAPMODE', 'DYNMODE')}
        self.entities = {}
        self.interfaces = {}
        self.order = []
        self.curves = {}
        self.document = 'drawing-A'
        self.angle = 0.
        self.origin = [0., 0., 0.]
        self.messages = []
        self.logs = []
        self.commands = []
        self.input_calls = []
        self.labels = []
        self.native_points = []
        self.offset_inputs = []
        self.mode = None
        self.native_active = 1
        self.native_names = 'HLPLBH HLBH'
        self.frozen_prompt = None
        self.omit_prompt = False
        self.append_start_to_prompt = False
        self.abort_returns_nil = False
        self.palette_number = 12
        self.missing_command = False
        self.incorrect_prompt = False
        self.select_mismatch = False
        self.unknown_text = False
        self.readonly_text = False
        self.initial_text = None
        self.extra_text = False
        self.ignore_write = False
        self.format_text = False
        self.native_height = None
        self.create_mark_on_pick = False
        self.fail_row = None
        self.mutate_source_only = False
        self.close_undo_group = False
        self.corrupt_after_exit = False
        self.change_type_after_exit = False
        self.refuse_cancel = False
        self.ignore_escape = False
        self.reject_landing = False
        self.cancel_refusals = 0
        self.undo_calls = 0
        self.undo_snapshot = None
        self.selection = []
        self.start_input = 'ZE1'
        self.h.builtins.update({
            'GETVAR': lambda name: self.variables[name],
            'SETVAR': lambda name, value: self.variables.__setitem__(name, value),
            'ENTGET': lambda entity, *args: copy.deepcopy(self.entities.get(entity)),
            'ENTLAST': lambda: self.order[-1] if self.order else None,
            'ENTNEXT': self.entnext,
            'SSGET': self.ssget,
            'SSLENGTH': len,
            'SSNAME': lambda selection, index: selection[index],
            'GETSTRING': self.getstring,
            'GETREAL': self.getreal,
            'VLAX-CURVE-ISCLOSED': lambda entity: self.curves[entity].get('closed', False),
            'VLAX-CURVE-GETSTARTPOINT': lambda entity: self.curves[entity]['start'],
            'VLAX-CURVE-GETENDPOINT': lambda entity: self.curves[entity]['end'],
            'VLAX-CURVE-GETENDPARAM': lambda entity: 1.,
            'VLAX-CURVE-GETDISTATPARAM': lambda entity, param: self.curve_length(entity),
            'VLAX-CURVE-GETPOINTATDIST': self.curve_point,
            'TRANS': self.trans,
            'VLAX-GET-ACAD-OBJECT': lambda: 'application',
            'VLA-GET-ACTIVEDOCUMENT': lambda application: self.document,
            'VLAX-ENAME->VLA-OBJECT': lambda entity: entity,
            'VLAX-PROPERTY-AVAILABLE-P': self.available,
            'VLAX-GET-PROPERTY': lambda entity, prop: self.interfaces[entity][str(prop)]['value'],
            'VLAX-PUT-PROPERTY': self.put_property,
            'VLA-UPDATE': lambda entity: None,
            'COMMAND': self.command,
            'COMMAND-S': self.command_s,
            'VL-CATCH-ALL-APPLY': self.catch,
            'PRINC': lambda *args: self.messages.extend(args),
            'HLBN:LOG': lambda stage, data: self.logs.append((stage, copy.deepcopy(data))) or 'C:/Temp/HLPLBH-debug.log',
            'EXIT': lambda: self.abort(),
        })

    def abort(self):
        raise NativeAbort('quit / exit abort')

    def catch(self, function, args):
        if self.abort_returns_nil and function == 'HLBN:NATIVERUN':
            try:
                return self.h.call(function, args)
            except NativeAbort:
                return None
        return self.h.catch(function, args)

    def call(self, name, *values):
        return self.h.call(Symbol(name.upper()), list(values))

    def trans(self, point, source, target):
        if source == target:
            return list(point)
        cosine, sine = math.cos(self.angle), math.sin(self.angle)
        if (source, target) == (1, 0):
            x, y, z = point
            return [self.origin[0] + cosine*x - sine*y,
                    self.origin[1] + sine*x + cosine*y, self.origin[2] + z]
        if (source, target) == (0, 1):
            x, y, z = [point[i] - self.origin[i] for i in range(3)]
            return [cosine*x + sine*y, -sine*x + cosine*y, z]
        self.fail(f'unexpected coordinate spaces {source}, {target}')

    def add_entity(self, name, kind, start=None, end=None, closed=False, text=None, flags=None):
        data = [Pair(-1, name), Pair(0, kind), Pair(5, name), Pair(8, 'wire-layer')]
        if start is not None:
            start, end = self.trans(start, 1, 0), self.trans(end, 1, 0)
            data += [Pair(10, start), Pair(11, end)]
            self.curves[name] = {'start': start, 'end': end, 'closed': closed}
        if text is not None:
            data.append(Pair(1, text))
        if flags is not None:
            data.append(Pair(70, flags))
        self.entities[name] = data
        self.order.append(name)
        return name

    def wire(self, name, y, x=100., kind='LINE'):
        return self.add_entity(name, kind, [x-50., y, 0.], [x+50., y, 0.])

    def entnext(self, entity=None):
        if entity is None:
            return self.order[0] if self.order else None
        index = self.order.index(entity) + 1
        return self.order[index] if index < len(self.order) else None

    def curve_length(self, entity):
        curve = self.curves[entity]
        points = curve.get('points', [curve['start'], curve['end']])
        return sum(math.dist(a, b) for a, b in zip(points, points[1:]))

    def curve_point(self, entity, distance):
        curve = self.curves[entity]
        points = curve.get('points', [curve['start'], curve['end']])
        for start, end in zip(points, points[1:]):
            length = math.dist(start, end)
            if distance <= length:
                fraction = distance / length
                return [a + (b-a)*fraction for a, b in zip(start, end)]
            distance -= length
        return list(points[-1])

    def ssget(self, mode):
        self.input_calls.append(('selection', mode))
        return self.selection or None

    def getstring(self, *args):
        self.input_calls.append(('number', args))
        return self.start_input

    def getreal(self, *args):
        self.input_calls.append(('offset', args))
        return self.offset_inputs.pop(0) if self.offset_inputs else None

    def point_argument(self, args):
        if (len(args) != 1 or not isinstance(args[0], list) or len(args[0]) != 3
                or not all(isinstance(value, (int, float)) for value in args[0])):
            self.variables['LASTPROMPT'] = '点无效。'
            raise NativeAbort('point rejected: HLBH needs one coordinate, not an entity/pick list')
        return list(args[0])

    def available(self, entity, prop, writable=None):
        info = self.interfaces.get(entity, {}).get(str(prop))
        return info is not None and (not writable or info['writable'])

    def put_property(self, entity, prop, value):
        self.assertTrue(self.available(entity, prop, True))
        if not self.ignore_write:
            self.interfaces[entity][str(prop)]['value'] = value
            data = self.entities[entity]
            self.entities[entity] = [Pair(1, value) if isinstance(p, Pair) and p.car == 1 else p for p in data]

    def set_mode(self, mode):
        self.mode = mode
        self.variables['CMDACTIVE'] = self.native_active if mode else 0
        self.variables['CMDNAMES'] = self.native_names if mode else ''
        self.variables['LASTPROMPT'] = {'wire': '请选择要标注的导线 <退出>:',
                                        'landing': '请给出文字装落点<退出>:'}.get(mode, '命令:')
        if mode and self.frozen_prompt is not None:
            self.variables['LASTPROMPT'] = self.frozen_prompt
        if mode and self.omit_prompt:
            self.variables['LASTPROMPT'] = None

    def command(self, *args):
        self.commands.append(args)
        if not args:
            if self.cancel_refusals > 0:
                self.cancel_refusals -= 1
            elif not self.refuse_cancel and not self.ignore_escape:
                self.set_mode(None)
            return
        if args == ('HLBH',):
            before = self.variables['LASTPROMPT']
            if self.missing_command:
                self.set_mode(None)
                self.variables['LASTPROMPT'] = '未知命令 HLBH'
            else:
                self.set_mode('wire')
                if self.incorrect_prompt:
                    self.variables['LASTPROMPT'] = '该版本的其他设置提示'
                if self.append_start_to_prompt:
                    self.frozen_prompt = before + ' HLBH'
                    self.variables['LASTPROMPT'] = self.frozen_prompt
            return
        if args == ('',):
            self.assertIn(self.mode, ('wire', 'landing'))
            if self.cancel_refusals > 0:
                self.cancel_refusals -= 1
                return
            if self.refuse_cancel:
                return
            if self.mode == 'landing':
                self.set_mode('wire')
                return
            self.set_mode(None)
            if self.corrupt_after_exit:
                self.put_property(self.labels[0]['label'], Symbol('TEXTSTRING'), 'wrong1')
            if self.change_type_after_exit:
                label = self.labels[0]['label']
                self.entities[label] = [Pair(0, 'TEXT') if p.car == 0 else p for p in self.entities[label]]
            return
        if self.mode == 'wire':
            point = self.point_argument(args)
            candidates = [name for name in self.curves
                          if math.dist(point, self.trans(self.curve_point(name, self.curve_length(name)/2), 0, 1)) < 1e-6]
            if len(candidates) != 1:
                self.variables['LASTPROMPT'] = '选择无效，重新选择! 请选取要标注的导线 <退出>:'
                raise NativeAbort('point does not identify one selected wire midpoint')
            entity = candidates[0]
            self.selected = entity
            self.selected_point = list(point)
            self.native_points.append(('wire', entity, list(point)))
            if self.select_mismatch:
                if self.frozen_prompt is None:
                    self.variables['LASTPROMPT'] = '选择无效，重新选择! 请选取要标注的导线 <退出>:'
                return
            if self.create_mark_on_pick:
                self.add_entity(f'pick-mark-{len(self.labels)+1}', 'LINE')
            self.set_mode('landing')
            return
        self.assertEqual(self.mode, 'landing')
        point = self.point_argument(args)
        self.native_points.append(('landing', self.selected, list(point)))
        if self.reject_landing:
            self.variables['LASTPROMPT'] = '点无效。'
            raise NativeAbort('native landing point rejected')
        index = len(self.labels) + 1
        if self.mutate_source_only:
            self.entities[self.selected].append(Pair(1, 'native source change'))
            raise RuntimeError('native failed after modifying source')
        self.add_entity(f'leader-{index}', 'LINE')
        self.add_entity(f'slash-{index}', 'LINE')
        text = self.initial_text if self.initial_text is not None else f'wl{self.palette_number}'
        if self.format_text:
            text = '{\\H2;ZE1}'
        label = self.add_entity(f'label-{index}', 'TCH_TEXT', text=text)
        if not self.unknown_text:
            self.interfaces[label] = {'TEXTSTRING': {'value': text, 'writable': not self.readonly_text}}
            if self.native_height is not None:
                self.interfaces[label]['HEIGHT'] = {'value': self.native_height, 'writable': False}
        if self.extra_text:
            extra = self.add_entity(f'extra-{index}', 'TCH_TEXT', text='ZE99')
            self.interfaces[extra] = {'TEXTSTRING': {'value': 'ZE99', 'writable': True}}
        self.labels.append({'label': label, 'wire': self.selected,
                            'pick': self.selected_point, 'landing': point})
        self.palette_number += 1
        self.set_mode('wire')
        if self.close_undo_group:
            self.variables['UNDOCTL'] &= ~8
        if self.fail_row == index:
            raise RuntimeError('Function cancelled')

    def command_s(self, *args):
        self.commands.append(args)
        self.assertIsNone(self.mode, 'never execute UNDO while the vendor still waits for input')
        self.assertEqual(self.variables['CMDACTIVE'], 0, 'never execute UNDO over active native command')
        if args == ('_.UNDO', '_Begin'):
            self.undo_snapshot = copy.deepcopy((self.entities, self.interfaces, self.order))
            self.variables['UNDOCTL'] |= 8
            self.variables['LASTPROMPT'] = '输入要放弃的操作数目或 [自动(A)/控制(C)/开始(BE)/结束(E)/标记(M)/后退(B)] <1>: _Begin'
        elif args == ('_.UNDO', '_End'):
            self.assertTrue(self.variables['UNDOCTL'] & 8)
            self.variables['UNDOCTL'] &= ~8
        elif args == ('_.U',):
            self.undo_calls += 1
            self.entities, self.interfaces, self.order = copy.deepcopy(self.undo_snapshot)
        else:
            self.fail(f'unexpected batch command {args}')

    def plan(self, names, start='ZE1', offset=None):
        rows, skipped = self.call('HLBN:Rows', names)
        self.assertEqual(skipped, 0)
        return self.call('HLBN:Plan', rows, self.call('HLBN:NumberParts', start),
                         offset if offset is not None else [500., 500., 0.])

    def values(self, records, key):
        return [self.call('HLBN:Get', Symbol(key.upper()), record) for record in records]

    def assert_vars_restored(self):
        self.assertEqual({key: self.variables[key] for key in self.original_vars}, self.original_vars)


class NumberAndLayoutTests(BatchFixture):
    def test_prefix_zero_padding_and_width_growth(self):
        for start, expected in [('ZE1', ['ZE1', 'ZE2', 'ZE3']),
                                ('4ALE(JZ)-ZE009', ['4ALE(JZ)-ZE009', '4ALE(JZ)-ZE010', '4ALE(JZ)-ZE011']),
                                ('ZE99', ['ZE99', 'ZE100', 'ZE101']),
                                ('0', ['0', '1', '2'])]:
            with self.subTest(start=start):
                parts = self.call('HLBN:NumberParts', start)
                self.assertEqual([self.call('HLBN:NumberAt', parts, i) for i in range(3)], expected)

    def test_reject_invalid_or_overflow_without_rounding(self):
        for start in ('', 'ZE', 'ZE1a', 'ZE2147483648', 'ZE99999999999', 'Z'*257+'1', '{ZE1', 'Z\\E1'):
            with self.subTest(start=start):
                self.assertIsNone(self.call('HLBN:NumberParts', start))
        parts = self.call('HLBN:NumberParts', 'ZE2147483647')
        self.assertEqual(self.call('HLBN:NumberAt', parts, 0), 'ZE2147483647')
        self.assertIsNone(self.call('HLBN:NumberAt', parts, 1))

    def test_window_selection_order_is_replaced_with_top_to_bottom(self):
        names = [self.wire(f'wire-{i}', 1000.-100*i) for i in range(5)]
        plan = self.plan([names[3], names[0], names[4], names[1], names[2]])
        self.assertEqual(self.values(plan, 'entity'), names)
        self.assertEqual(self.values(plan, 'label'), [f'ZE{i}' for i in range(1, 6)])
        self.assertEqual(self.values(plan, 'landing'), [[600., 1500.-100*i, 0.] for i in range(5)])

    def test_same_height_uses_left_to_right_and_preserves_exact_per_wire_offset(self):
        right = self.wire('right', 10., 200.)
        left = self.wire('left', 10., 100.)
        below = self.wire('below', 9., 100.)
        plan = self.plan([below, right, left])
        self.assertEqual(self.values(plan, 'entity'), [left, right, below])
        self.assertEqual(self.values(plan, 'landing'), [[600., 510., 0.], [700., 510., 0.], [600., 509., 0.]])

    def test_rotated_translated_ucs_is_used_for_selection_order_and_points(self):
        self.angle = math.pi/2
        self.origin = [10000., 20000., 300.]
        names = [self.wire('top', 1000.), self.wire('bottom', 500.)]
        plan = self.plan(list(reversed(names)))
        self.assertEqual(self.values(plan, 'entity'), names)
        self.call('HLBN:Execute', plan)
        for label in self.labels:
            self.assertAlmostEqual(label['pick'][0], 100.)
        self.assertEqual(self.labels[0]['landing'], [600., 1500., 0.])
        self.assert_vars_restored()

    def test_skip_text_blocks_closed_unsupported_and_3d_polylines(self):
        valid = self.wire('valid', 100.)
        poly = self.add_entity('poly', 'LWPOLYLINE', [0., 90., 0.], [100., 90., 0.])
        native = self.wire('native', 80., kind='TCH_ELEC_WIRE')
        closed = self.add_entity('closed', 'LWPOLYLINE', [0., 70., 0.], [100., 70., 0.], closed=True)
        three_d = self.add_entity('three-d', 'POLYLINE', [0., 60., 0.], [100., 60., 0.], flags=8)
        text = self.add_entity('text', 'TEXT')
        block = self.add_entity('block', 'INSERT')
        unsupported = self.add_entity('proxy', 'TCH_OTHER')
        rows, skipped = self.call('HLBN:Rows', [valid, poly, native, closed, three_d, text, block, unsupported])
        self.assertEqual(self.values(rows, 'entity'), [native, poly, valid])
        self.assertEqual(skipped, 5)

    def test_ambiguous_overlapping_connections_rejected_before_native_write(self):
        names = [self.wire('a', 100.), self.wire('b', 100.)]
        with self.assertRaises(RuntimeError):
            self.plan(names)
        self.assertEqual(self.commands, [])

    def test_cross_elevation_and_invalid_offsets_rejected_before_native_write(self):
        wire = self.wire('wire', 100.)
        for offset in ([0., 0., 0.], [500., 500., 1.], [500., 500.]):
            with self.subTest(offset=offset), self.assertRaises(RuntimeError):
                self.plan([wire], offset=offset)
        sloped = self.add_entity('sloped', 'LINE', [0., 0., 0.], [100., 0., 1.])
        with self.assertRaises(RuntimeError):
            self.plan([sloped])
        higher = self.add_entity('higher', 'LINE', [0., 0., 1.], [100., 0., 1.])
        with self.assertRaises(RuntimeError):
            self.plan([wire, higher])
        self.assertEqual(self.commands, [])

    def test_sequence_overflow_rejected_before_native_write(self):
        names = [self.wire('a', 100.), self.wire('b', 90.)]
        with self.assertRaises(RuntimeError):
            self.plan(names, start='ZE2147483647')
        self.assertEqual(self.commands, [])

    def test_offset_setting_accepts_negative_values_and_enter_preserves_values(self):
        self.offset_inputs = [-200., 300.]
        self.call('C:HLPLBHSET')
        self.assertEqual(self.call('HLBN:DefaultOffset'), [-200., 300., 0.])
        self.call('C:HLPLBHSET')
        self.assertEqual(self.call('HLBN:DefaultOffset'), [-200., 300., 0.])
        self.offset_inputs = [0., 0.]
        self.call('C:HLPLBHSET')
        self.assertEqual(self.call('HLBN:DefaultOffset'), [-200., 300., 0.])


class NativeProtocolTests(BatchFixture):
    def test_full_two_input_workflow_native_types_and_two_points_per_row(self):
        names = [self.wire(f'wire-{i}', 1000.-100*i) for i in range(5)]
        original_sources = copy.deepcopy(self.entities)
        self.selection = [names[4], names[1], names[3], names[0], names[2]]
        self.call('C:HLPLBH')
        self.assertEqual([kind for kind, _ in self.input_calls], ['number', 'selection'])
        self.assertEqual([item['wire'] for item in self.labels], names)
        self.assertEqual([self.interfaces[item['label']]['TEXTSTRING']['value'] for item in self.labels],
                         [f'ZE{i}' for i in range(1, 6)])
        for name, data in original_sources.items():
            self.assertEqual(self.entities[name], data)
        self.assertTrue(all(field(self.entities[item['label']], 0) == 'TCH_TEXT' for item in self.labels))
        self.assertEqual(sum(command == ('HLBH',) for command in self.commands), 1)
        self.assertEqual(len(self.native_points), 10)
        self.assertEqual(self.variables['CMDACTIVE'], 0)
        self.assertEqual(self.variables['UNDOCTL'], 1)
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
        self.assertEqual(self.undo_calls, 0)
        self.assert_vars_restored()
        self.assertIn('COMPLETE', [stage for stage, data in self.logs])

    def test_readonly_number_already_matching_is_preserved(self):
        self.readonly_text = True
        self.initial_text = 'ZE1'
        result = self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)]))
        self.assertTrue(truth(result))
        self.assertEqual(self.interfaces['label-1']['TEXTSTRING']['value'], 'ZE1')

    def test_interface_failures_undo_only_our_native_batch(self):
        for failure in ('unknown_text', 'readonly_text', 'extra_text', 'ignore_write', 'format_text'):
            with self.subTest(failure=failure):
                self.setUp()
                names = [self.wire('one', 100.), self.wire('two', 90.)]
                before = copy.deepcopy(self.entities)
                setattr(self, failure, True)
                self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
                self.assertEqual(self.entities, before)
                self.assertEqual(self.undo_calls, 1)
                self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
                self.assert_vars_restored()
                self.assertNotIn('COMPLETE', [stage for stage, data in self.logs])

    def test_missing_command_or_prompt_mismatch_does_not_undo_previous_user_work(self):
        for failure in ('missing_command', 'incorrect_prompt', 'select_mismatch'):
            with self.subTest(failure=failure):
                self.setUp()
                names = [self.wire('wire', 100.)]
                before = copy.deepcopy(self.entities)
                setattr(self, failure, True)
                self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
                self.assertEqual(self.entities, before)
                self.assertEqual(self.undo_calls, 0)
                self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
                self.assert_vars_restored()
                if failure != 'select_mismatch':
                    self.assertFalse(any(command and isinstance(command[0], list) for command in self.commands))

    def test_native_cancel_mid_batch_rolls_back_all_created_components(self):
        names = [self.wire(f'wire-{i}', 1000.-100*i) for i in range(5)]
        before = copy.deepcopy(self.entities)
        self.fail_row = 3
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual(len(self.labels), 3)
        self.assertEqual(self.entities, before)
        self.assertEqual(self.undo_calls, 1)
        self.assert_vars_restored()

    def test_native_source_change_without_new_entity_is_also_undone(self):
        names = [self.wire('wire', 100.)]
        before = copy.deepcopy(self.entities)
        self.mutate_source_only = True
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual(self.entities, before)
        self.assertEqual(self.undo_calls, 1)

    def test_final_readback_detects_vendor_change_after_exit(self):
        names = [self.wire('a', 100.), self.wire('b', 90.)]
        before = copy.deepcopy(self.entities)
        self.corrupt_after_exit = True
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual(self.entities, before)
        self.assertEqual(self.undo_calls, 1)

    def test_final_readback_rejects_native_type_replacement(self):
        names = [self.wire('wire', 100.)]
        before = copy.deepcopy(self.entities)
        self.change_type_after_exit = True
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual(self.entities, before)
        self.assertEqual(self.undo_calls, 1)

    def test_native_height_does_not_change_the_user_confirmed_fixed_offset(self):
        names = [self.wire(f'wire-{i}', 100.-i) for i in range(5)]
        self.native_height = 20.
        result = self.call('HLBN:Execute', self.plan(names))
        self.assertTrue(truth(result))
        self.assertEqual([label['landing'][0] for label in self.labels], [600.]*5)
        self.assertEqual([label['landing'][1] for label in self.labels], [600.-i for i in range(5)])

    def test_undo_disabled_one_step_or_existing_group_blocks_before_write(self):
        plan = self.plan([self.wire('wire', 100.)])
        for undoctl in (0, 3, 9):
            with self.subTest(undoctl=undoctl):
                self.variables['UNDOCTL'] = undoctl
                with self.assertRaises(RuntimeError):
                    self.call('HLBN:Execute', plan)
                self.assertEqual(self.commands, [])
                self.assert_vars_restored()

    def test_recovery_in_another_document_does_not_change_its_state(self):
        self.unknown_text = True
        self.refuse_cancel = True
        self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)]))
        self.assertTrue(truth(self.h.lookup('*HLBN:PENDING*')))
        self.document = 'drawing-B'
        self.set_mode('wire')
        self.variables['OSMODE'] = 99
        before_commands = list(self.commands)
        self.call('C:HLPLBHRECOVER')
        self.assertEqual(self.commands, before_commands)
        self.assertEqual(self.variables['OSMODE'], 99)
        self.assertTrue(truth(self.h.lookup('*HLBN:PENDING*')))
        self.document = 'drawing-A'
        self.refuse_cancel = False
        self.set_mode(None)  # User presses Esc before invoking the recovery command.
        self.call('C:HLPLBHRECOVER')
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
        self.assertEqual(self.undo_calls, 1)

    def test_changed_vendor_undo_group_is_reported_without_undoing_unrelated_history(self):
        self.close_undo_group = True
        self.assertIsNone(self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)])))
        self.assertTrue(truth(self.h.lookup('*HLBN:PENDING*')))
        self.assertEqual(self.undo_calls, 0)
        self.assertNotIn('COMPLETE', [stage for stage, data in self.logs])
        self.assert_vars_restored()
        # The user may undo this vendor-created group manually, then verify recovery.
        self.command_s('_.U')
        self.call('C:HLPLBHRECOVER')
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))

    def test_recovery_refuses_to_undo_drawing_work_added_after_failure(self):
        self.unknown_text = True
        self.refuse_cancel = True
        self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)]))
        self.assertTrue(truth(self.h.lookup('*HLBN:PENDING*')))
        self.add_entity('later-work', 'TEXT', text='keep later work')
        self.refuse_cancel = False
        self.set_mode(None)
        self.call('C:HLPLBHRECOVER')
        self.assertIn('later-work', self.entities)
        self.assertEqual(self.undo_calls, 0)
        self.assertTrue(truth(self.h.lookup('*HLBN:PENDING*')))

    def test_empty_or_unsupported_selection_makes_no_native_changes(self):
        self.call('C:HLPLBH')
        self.assertEqual(self.commands, [])
        self.assertEqual([kind for kind, _ in self.input_calls], ['number', 'selection'])
        self.input_calls = []
        self.selection = [self.add_entity('text', 'TEXT')]
        with self.assertRaises(RuntimeError):
            self.call('C:HLPLBH')
        self.assertEqual(self.commands, [])

    def test_enter_uses_default_start_number(self):
        self.start_input = ''
        self.selection = [self.wire('wire', 100.)]
        self.call('C:HLPLBH')
        self.assertEqual(self.interfaces['label-1']['TEXTSTRING']['value'], 'ZE1')


class NativePromptRegressionTests(BatchFixture):
    def test_user_log_cached_undo_prompt_completes_five_rows_without_more_user_input(self):
        self.frozen_prompt = '输入要放弃的操作数目或 [自动(A)/控制(C)/开始(BE)/结束(E)/标记(M)/后退(B)] <1>: _Begin HLBH'
        self.selection = [self.wire(f'wire-{i}', 1000.-i*100) for i in range(5)]
        self.call('C:HLPLBH')
        self.assertEqual([kind for kind, _ in self.input_calls], ['number', 'selection'])
        self.assertEqual([self.interfaces[row['label']]['TEXTSTRING']['value'] for row in self.labels],
                         [f'ZE{i}' for i in range(1, 6)])
        self.assertIsNone(self.mode)
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
        self.assertIn('COMPLETE', [stage for stage, _ in self.logs])
        self.assert_vars_restored()

    def test_cached_prompt_with_echoed_command_suffix_is_not_a_new_native_prompt(self):
        self.append_start_to_prompt = True
        result = self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)]))
        self.assertTrue(truth(result))
        self.assertIn('_Begin HLBH', self.frozen_prompt)
        self.assertIsNone(self.mode)

    def test_arx_activity_and_internal_command_names_are_supported(self):
        for activity, names in ((64, 'VENDOR_CIRCUIT_NUMBER'), (65, 'HLBH'),
                                (0, 'HLBH'), (64, '')):
            with self.subTest(activity=activity, names=names):
                self.setUp()
                self.native_active, self.native_names = activity, names
                result = self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)]))
                self.assertTrue(truth(result))
                self.assertEqual(self.interfaces['label-1']['TEXTSTRING']['value'], 'ZE1')
                self.assertIsNone(self.mode)
                self.assert_vars_restored()

    def test_nil_return_after_prompt_abort_is_failure_and_exits_native_first(self):
        self.abort_returns_nil = True
        self.incorrect_prompt = True
        names = [self.wire('wire', 100.)]
        before = copy.deepcopy(self.entities)
        result = self.call('HLBN:Execute', self.plan(names))
        self.assertIsNone(result)
        self.assertEqual(self.entities, before)
        self.assertIsNone(self.mode)
        self.assertNotIn('COMPLETE', [stage for stage, _ in self.logs])
        self.assertIn('FAILED', [stage for stage, _ in self.logs])
        self.assertEqual(self.undo_calls, 0)
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
        self.assert_vars_restored()

    def test_nil_return_after_partial_native_generation_rolls_back(self):
        self.abort_returns_nil = True
        self.readonly_text = True
        names = [self.wire('a', 100.), self.wire('b', 90.)]
        before = copy.deepcopy(self.entities)
        result = self.call('HLBN:Execute', self.plan(names))
        self.assertIsNone(result)
        self.assertEqual(self.entities, before)
        self.assertEqual(self.undo_calls, 1)
        self.assertIsNone(self.mode)
        self.assertNotIn('COMPLETE', [stage for stage, _ in self.logs])
        self.assert_vars_restored()

    def test_fresh_opposite_prompt_stops_before_sending_the_landing_point(self):
        self.select_mismatch = True
        self.native_active = 64
        self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)]))
        self.assertEqual([stage for stage, _, _ in self.native_points], ['wire'])
        self.assertIsNone(self.mode)
        self.assertEqual(self.undo_calls, 0)
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))

    def test_selection_rejected_with_a_cached_prompt_never_counts_as_complete(self):
        self.frozen_prompt = 'UNDO: _Begin HLBH'
        self.select_mismatch = True
        names = [self.wire('wire', 100.)]
        before = copy.deepcopy(self.entities)
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual(self.entities, before)
        self.assertIsNone(self.mode)
        self.assertEqual(self.undo_calls, 0)
        self.assertNotIn('COMPLETE', [stage for stage, _ in self.logs])

    def test_two_empty_exits_are_allowed_before_undo_and_stop_at_vendor_exit(self):
        self.native_active = 64
        self.native_names = 'VENDOR_CIRCUIT_NUMBER'
        self.unknown_text = True
        self.cancel_refusals = 1
        names = [self.wire('wire', 100.)]
        before = copy.deepcopy(self.entities)
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual(self.entities, before)
        self.assertEqual(self.commands.count(('',)), 2)
        self.assertEqual(self.undo_calls, 1)
        self.assertIsNone(self.mode)
        self.assert_vars_restored()

    def test_arx_that_refuses_cancel_blocks_undo_until_user_esc_then_recovery(self):
        self.native_active = 64
        self.unknown_text = True
        self.refuse_cancel = True
        self.assertIsNone(self.call('HLBN:Execute', self.plan([self.wire('wire', 100.)])))
        self.assertTrue(truth(self.h.lookup('*HLBN:PENDING*')))
        self.assertNotIn(('_.UNDO', '_End'), self.commands)
        self.assertEqual(self.undo_calls, 0)
        before_commands = list(self.commands)
        self.call('C:HLPLBHRECOVER')
        self.assertEqual(self.commands, before_commands)
        self.refuse_cancel = False
        self.set_mode(None)
        self.call('C:HLPLBHRECOVER')
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
        self.assertEqual(self.undo_calls, 1)
        self.assert_vars_restored()

    def test_active_arx_or_dialog_blocks_new_batch_before_requesting_user_input(self):
        for activity in (64, 65, 8):
            with self.subTest(activity=activity):
                self.setUp()
                self.variables['CMDACTIVE'] = activity
                self.call('C:HLPLBH')
                self.assertEqual(self.input_calls, [])
                self.assertEqual(self.commands, [])

    def test_short_result_is_not_a_complete_batch(self):
        names = [self.wire('a', 100.), self.wire('b', 90.)]
        self.h.builtins['HLBN:NATIVERUN'] = lambda plan: [['label', 'ZE1', 'TCH_TEXT']]
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertNotIn('COMPLETE', [stage for stage, _ in self.logs])
        self.assertEqual(self.undo_calls, 0)

    def test_unavailable_lastprompt_does_not_abort_a_verified_arx_batch(self):
        self.omit_prompt = True
        self.native_active = 64
        names = [self.wire('a', 100.), self.wire('b', 90.)]
        result = self.call('HLBN:Execute', self.plan(names))
        self.assertEqual([row[1] for row in result], ['ZE1', 'ZE2'])
        self.assertIsNone(self.mode)
        self.assert_vars_restored()


class NativeCoordinateTests(BatchFixture):
    def test_each_wire_receives_exactly_two_plain_coordinate_points_before_next_wire(self):
        names = [self.wire(f'wire-{i}', 1000.-100*i, x=100.+20*i) for i in range(5)]
        plan = self.plan(list(reversed(names)))
        result = self.call('HLBN:Execute', plan)
        self.assertTrue(truth(result))
        expected = []
        for row in plan:
            entity = self.call('HLBN:Get', Symbol('ENTITY'), row)
            expected.extend([('wire', entity, self.call('HLBN:Get', Symbol('PICK'), row)),
                             ('landing', entity, self.call('HLBN:Get', Symbol('LANDING'), row))])
        self.assertEqual(self.native_points, expected)
        self.assertEqual([stage for stage, _ in self.logs if stage in ('ROW_BEGIN', 'ROW_COMPLETE')],
                         ['ROW_BEGIN', 'ROW_COMPLETE']*5)
        self.assertEqual([row[1] for row in result], [f'ZE{i}' for i in range(1, 6)])
        self.assertIsNone(self.mode)
        self.assert_vars_restored()

    def test_polyline_pick_is_on_the_curve_at_half_length(self):
        poly = self.add_entity('poly', 'LWPOLYLINE', [0., 0., 0.], [100., 300., 0.])
        self.curves[poly]['points'] = [[0., 0., 0.], [100., 0., 0.], [100., 300., 0.]]
        result = self.call('HLBN:Execute', self.plan([poly]))
        self.assertTrue(truth(result))
        self.assertEqual(self.native_points, [('wire', poly, [100., 100., 0.]),
                                              ('landing', poly, [600., 600., 0.])])

    def test_failed_second_point_stops_before_the_next_wire_and_exits_both_stages(self):
        self.reject_landing = True
        self.abort_returns_nil = True
        names = [self.wire('top', 100.), self.wire('bottom', 90.)]
        before = copy.deepcopy(self.entities)
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual([stage for stage, _, _ in self.native_points], ['wire', 'landing'])
        self.assertEqual(self.entities, before)
        self.assertIsNone(self.mode)
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))
        self.assertEqual(self.undo_calls, 0)

    def test_vendor_that_ignores_escape_can_exit_with_empty_input_before_undo(self):
        self.ignore_escape = True
        self.unknown_text = True
        names = [self.wire('wire', 100.)]
        before = copy.deepcopy(self.entities)
        self.assertIsNone(self.call('HLBN:Execute', self.plan(names)))
        self.assertEqual(self.entities, before)
        self.assertIsNone(self.mode)
        self.assertEqual(self.undo_calls, 1)
        self.assertIsNone(self.h.lookup('*HLBN:PENDING*'))

    def test_mark_created_at_first_point_is_kept_with_the_same_native_annotation(self):
        self.create_mark_on_pick = True
        names = [self.wire('wire', 100.)]
        result = self.call('HLBN:Execute', self.plan(names))
        self.assertTrue(truth(result))
        self.assertIn('pick-mark-1', self.entities)
        self.assertEqual(self.interfaces['label-1']['TEXTSTRING']['value'], 'ZE1')
        self.assertEqual([stage for stage, _, _ in self.native_points], ['wire', 'landing'])
        self.assertIsNone(self.mode)

    def test_main_command_reuses_custom_offset_without_asking_for_a_blank_point(self):
        self.offset_inputs = [-500., -250.]
        self.call('C:HLPLBHSET')
        self.input_calls.clear()
        self.selection = [self.wire('wire', 100.)]
        self.call('C:HLPLBH')
        self.assertEqual([kind for kind, _ in self.input_calls], ['number', 'selection'])
        self.assertEqual(self.labels[0]['landing'], [-400., -150., 0.])
        self.assert_vars_restored()


class SourceTests(unittest.TestCase):
    def test_standalone_source_parses_and_strictly_roundtrips_gb2312(self):
        text = SOURCE.read_text(encoding='utf-8')
        self.assertEqual(text.encode('gb2312', errors='strict').decode('gb2312'), text)
        forms = parse(text)
        definitions = {str(form[1]) for form in forms if isinstance(form, list) and form[0] == 'DEFUN'}
        self.assertTrue({'C:HLPLBH', 'C:HLPLBHSET', 'C:HLPLBHRECOVER'}.issubset(definitions))
        self.assertNotIn('entmake', text.lower())
        self.assertNotIn('explode', text.lower())

    def test_export_creates_only_a_single_strict_gb2312_file(self):
        spec = importlib.util.spec_from_file_location('batch_number_export', ROOT / 'tools/export_batch_number.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        checks = ROOT / 'output/cad2020-hlbh-check'
        checks.mkdir(exist_ok=True)
        self.assertTrue(checks.resolve().is_relative_to(ROOT))
        with tempfile.TemporaryDirectory(dir=checks) as folder:
            destination = Path(folder) / 'HLPLBH.lsp'
            result = module.export(destination=destination)
            self.assertEqual(destination.read_bytes().decode('gb2312'), SOURCE.read_text(encoding='utf-8'))
            self.assertFalse(result['packaged'])
            self.assertEqual(len(list(Path(folder).iterdir())), 1)
            self.assertEqual(parse(destination.read_bytes().decode('gb2312')), parse(SOURCE.read_text(encoding='utf-8')))

    def test_export_rejects_unsupported_character_and_keeps_previous_file(self):
        spec = importlib.util.spec_from_file_location('batch_number_export', ROOT / 'tools/export_batch_number.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        checks = ROOT / 'output/cad2020-hlbh-check'
        checks.mkdir(exist_ok=True)
        self.assertTrue(checks.resolve().is_relative_to(ROOT))
        with tempfile.TemporaryDirectory(dir=checks) as folder:
            source, destination = Path(folder) / 'source.lsp', Path(folder) / 'HLPLBH.lsp'
            source.write_text('(princ "emoji \\U0001f600")'.replace('\\U0001f600', chr(0x1f600)), encoding='utf-8')
            destination.write_bytes(b'previous export')
            with self.assertRaises(UnicodeEncodeError):
                module.export(source, destination)
            self.assertEqual(destination.read_bytes(), b'previous export')


if __name__ == '__main__':
    unittest.main()
