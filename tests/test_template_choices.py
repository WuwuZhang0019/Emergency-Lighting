"""Native-shaped dynamic values and understandable template choices. Date: 2026-10-09."""
from dataclasses import dataclass
import unittest
from autolisp_host import Pair, Symbol, lisp_type, truth
import test_kernel as kernel


@dataclass
class Variant:
    value: object


@dataclass
class SafeArray:
    values: list


class TemplateChoiceTests(unittest.TestCase):
    def setUp(self):
        kernel.KernelTests.setUp(self)
        self.cfg = self.h.lookup('CFG')
        self.messages, self.prompts, self.saved, self.updated = [], [], [], []
        self.answers = iter([])
        self.names = {'panel': 'dfgjhdrtyjtfgj4SADFG3', 'circuit': 'fghjftyuk'}
        self.properties = {
            'panel': [self.prop('可见性1', ['0.3kW', '0.6kW', '1kW'])],
            'circuit': [self.prop('可见性1', ['普通', '地面', '预留'])],
        }
        self.picks = iter([None, ['panel'], ['circuit']])
        self.h.frames[0].update({':VLAX-TRUE': -1, ':VLAX-FALSE': 0})

        def table(kind, name):
            if kind == 'STYLE':
                return [Pair(2, name), Pair(40, 0.)]
            if kind == 'BLOCK':
                return [Pair(2, name)]
            return None

        def ask(prompt):
            self.prompts.append(prompt)
            return next(self.answers)

        self.h.builtins.update({
            'TYPE': lambda v: Symbol('VARIANT') if isinstance(v, Variant) else
                Symbol('SAFEARRAY') if isinstance(v, SafeArray) else lisp_type(v),
            'VLAX-VARIANT-VALUE': lambda v: v.value,
            'VLAX-SAFEARRAY->LIST': lambda v: v.values,
            'VLAX-GET-PROPERTY': lambda p, key: p['allowed'],
            'VLAX-INVOKE': lambda obj, key: self.properties[obj],
            'VLAX-ENAME->VLA-OBJECT': lambda obj: obj,
            'VLA-GET-ISDYNAMICBLOCK': lambda obj: -1,
            'VLA-GET-READONLY': lambda p: p['readonly'],
            'VLA-GET-PROPERTYNAME': lambda p: p['name'],
            'VLA-GET-VALUE': lambda p: Variant(p.get('current', '0.3kW')),
            'VLAX-VARIANT-TYPE': lambda v: 8,
            'VLAX-MAKE-VARIANT': lambda value, kind: Variant(value),
            'VLA-PUT-VALUE': lambda p, v: (self.updated.append(v.value), p.update(current=v.value)),
            'EL:EFFECTIVENAME': lambda e: self.names[e],
            'EL:DEFINITIONDATA': lambda name, stack: ['definition', name],
            'EL:PICKENTITY': lambda prompt: self.fail('automatic template must not pick samples'),
            'SSGET': lambda *args: list(self.names),
            'SSLENGTH': len, 'SSNAME': lambda ss, i: ss[i],
            'ENTGET': lambda e: [Pair(0, 'INSERT'), Pair(5, e), Pair(2, self.names[e])],
            'HANDENT': lambda h: h,
            'TBLSEARCH': table,
            'GETVAR': lambda key: {'TEXTSTYLE': 'Standard', 'TEXTSIZE': 250.}.get(key),
            'GETINT': ask,
            'EL:LOADCONFIG': lambda: self.cfg,
            'EL:SAVECONFIG': lambda cfg: self.saved.append(cfg) or True,
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
            'PRINC': lambda *args: self.messages.extend(str(v) for v in args),
        })

    def prop(self, name, values, readonly=0):
        return {'name': name, 'readonly': readonly,
                'allowed': Variant(SafeArray([Variant(v) for v in values]))}

    def call(self, name, *args):
        return self.h.call(Symbol(name.upper()), list(args))

    def test_allowed_values_unwrap_each_variant_and_preserve_numbers(self):
        prop = self.prop('test', ['0.3kW', 0, 1.5])
        self.assertEqual(self.call('EL:AllowedValues', prop), ['0.3kW', 0, 1.5])
        prop['allowed'] = ['普通', '地面', '预留']
        self.assertEqual(self.call('EL:AllowedValues', prop), ['普通', '地面', '预留'])

    def test_screenshot_names_save_six_states_without_number_questions(self):
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(self.prompts, [])
        self.assertEqual(len(self.saved), 1)
        self.h.frames[0]['SAVED'] = self.saved[0]
        self.assertTrue(truth(self.h.run("(EL:TemplateValid (EL:Get 'template saved))")))
        self.assertTrue(truth(self.h.run('(EL:ConfigValid saved "test")')))
        text = ''.join(self.messages)
        for label in ('0.3kW', '0.6kW', '1kW', '普通', '地面', '预留', '已保存'):
            self.assertIn(label, text)
        self.assertNotIn('Variant', text)
        self.assertEqual(self.updated, [])  # Capture never switches the source block.

    def test_setting_native_property_uses_unwrapped_allowed_value(self):
        self.assertTrue(truth(self.call('EL:SetDynamicValue', 'panel', '可见性1', '0.6kW')))
        self.assertEqual(self.updated, ['0.6kW'])

    def test_manual_mapping_lists_meaning_and_retries_invalid_number(self):
        self.properties['panel'] = [self.prop('容量状态', ['小容量', '中容量', '大容量'])]
        self.answers = iter([9, 1, 1, 1])  # Menus shrink as already assigned values disappear.
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(len(self.saved), 1)
        text = ''.join(self.messages)
        for label in ('1. 小容量', '2. 中容量', '3. 大容量', '0.3kW', '超出范围', '0.6kW'):
            self.assertIn(label, text)
        self.assertTrue(all('回车取消' in p for p in self.prompts))

    def test_ambiguous_property_requires_named_choice(self):
        self.properties['panel'].append(self.prop('容量选项', ['0.3kW', '0.6kW', '1kW']))
        self.answers = iter([2])
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(len(self.prompts), 1)
        self.h.frames[0]['SAVED'] = self.saved[0]
        self.assertEqual(self.h.run("(EL:Get 'property (EL:Get 'panel (EL:Get 'template saved)))"), '容量选项')
        self.assertIn('1. 可见性1', ''.join(self.messages))
        self.assertIn('2. 容量选项', ''.join(self.messages))

    def test_enter_cancels_ambiguous_mapping_and_preserves_old_template(self):
        self.properties['panel'] = [self.prop('容量状态', ['小', '中', '大'])]
        self.answers = iter([None])
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(self.saved, [])
        self.assertEqual(len(self.prompts), 1)
        self.assertIn('取消', ''.join(self.messages))

    def test_readonly_and_empty_properties_do_not_become_choices(self):
        self.properties['panel'] = [self.prop('锁定容量', ['0.3kW', '0.6kW', '1kW'], -1),
                                    self.prop('距离', [])]
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(self.saved, [])
        self.assertEqual(self.prompts, [])
        self.assertIn('没有找到', ''.join(self.messages))

    def test_partly_named_values_reserve_known_meanings(self):
        self.properties['panel'] = [self.prop('容量状态', ['大容量', '0.6kW', '小容量'])]
        self.answers = iter([2, 1])
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(len(self.saved), 1)
        self.h.frames[0]['SAVED'] = self.saved[0]
        values = self.h.run("(mapcar '(lambda (s) (EL:Get 'value s)) (EL:Get 'states (EL:Get 'panel (EL:Get 'template saved))))")
        self.assertEqual(values, ['小容量', '0.6kW', '大容量'])

    def test_enter_cancels_property_choice_without_followup_questions(self):
        self.properties['panel'].append(self.prop('容量选项', ['0.3kW', '0.6kW', '1kW']))
        self.answers = iter([None])
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(self.saved, [])
        self.assertEqual(len(self.prompts), 1)
        self.assertIn('原模板保持不变', ''.join(self.messages))

    def test_numeric_states_remain_numbers_in_saved_config(self):
        self.properties['panel'] = [self.prop('容量', [0, 1, 2])]
        self.answers = iter([1, 1, 1])
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(len(self.saved), 1)
        self.h.frames[0]['SAVED'] = self.saved[0]
        values = self.h.run("(mapcar '(lambda (s) (EL:Get 'value s)) (EL:Get 'states (EL:Get 'panel (EL:Get 'template saved))))")
        self.assertEqual(values, [0, 1, 2])

    def test_config_write_failure_does_not_report_saved(self):
        self.h.builtins['EL:SAVECONFIG'] = lambda cfg: None
        self.h.run('(c:ELTEMPLATE)')
        text = ''.join(self.messages)
        self.assertIn('写入失败', text)
        self.assertNotIn('已保存', text)

    def test_invalid_or_duplicate_states_are_not_offered(self):
        self.properties['panel'] = [self.prop('空状态', ['0.3kW', None, '1kW']),
                                    self.prop('重复状态', ['小', '小', '大'])]
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(self.saved, [])
        self.assertEqual(self.prompts, [])
        self.assertIn('没有找到', ''.join(self.messages))

    def test_capacity_whitespace_and_fixed_buried_alias_are_automatic(self):
        self.properties['panel'] = [self.prop('可见性1', [' 0.3 kw ', '0.6kW', '1 kW'])]
        self.properties['circuit'] = [self.prop('可见性1', ['普通', '埋地', '预留'])]
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(self.prompts, [])
        self.assertEqual(len(self.saved), 1)
        self.h.frames[0]['SAVED'] = self.saved[0]
        self.assertEqual(self.h.run("(EL:Get 'value (EL:State 'cap1000 (EL:Get 'panel (EL:Get 'template saved))))"), '1 kW')
        self.assertEqual(self.h.run("(EL:Get 'value (EL:State 'ground (EL:Get 'circuit (EL:Get 'template saved))))"), '埋地')
        self.assertFalse(truth(self.call('EL:TemplateMatches', '埋地', Symbol('GROUND'), '箱体容量')))

    def test_multiple_alias_matches_require_explicit_choice(self):
        self.properties['circuit'] = [self.prop('可见性1', ['普通', '地面', '埋地', '预留'])]
        self.answers = iter([2])
        self.h.run('(c:ELTEMPLATE)')
        self.assertEqual(len(self.prompts), 1)
        self.assertIn('1. 地面', ''.join(self.messages))
        self.assertIn('2. 埋地', ''.join(self.messages))

    def test_capture_returns_template_without_saving_config(self):
        template = self.call('EL:CaptureFixedTemplate', self.cfg)
        self.assertTrue(truth(template))
        self.assertEqual(self.saved, [])

    def test_fixed_text_matches_user_properties_without_current_style_or_pick(self):
        self.h.builtins['GETVAR'] = lambda key: self.fail('text appearance must be fixed')
        self.h.run('(setq spec (EL:FixedText))')
        for key, value in [('style', '_TEL_DIM'), ('height', 350.), ('factor', .7),
                           ('align', 1), ('rotation', 0.), ('layer', 'TEL_TEXT')]:
            self.assertEqual(self.h.run(f"(EL:Get '{key} spec)"), value)

    def test_missing_block_prompts_copy_instead_of_picking(self):
        table = self.h.builtins['TBLSEARCH']
        self.h.builtins['SSGET'] = lambda *args: None
        self.h.builtins['TBLSEARCH'] = lambda kind, name: None if kind == 'BLOCK' else table(kind, name)
        self.assertIsNone(self.call('EL:CaptureFixedTemplate', self.cfg))
        self.assertIn('请将该图块拷入', ''.join(self.messages))
        self.assertIn('dfgjhdrtyjtfgj4SADFG3', ''.join(self.messages))
        self.assertEqual(self.saved, [])

    def test_definition_only_probes_are_deleted_and_do_not_save_dead_handles(self):
        deleted = []
        self.h.builtins.update({
            'SSGET': lambda *args: None,
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda app: 'doc',
            'VLA-GET-MODELSPACE': lambda doc: 'space',
            'VLAX-3D-POINT': lambda p: p,
            'VLA-INSERTBLOCK': lambda space, pos, name, *args: next(k for k, v in self.names.items() if v == name),
            'VLAX-VLA-OBJECT->ENAME': lambda obj: obj,
            'VLA-DELETE': lambda obj: deleted.append(obj),
        })
        self.h.frames[0]['CAPTURED'] = self.call('EL:CaptureFixedTemplate', self.cfg)
        self.assertTrue(truth(self.h.lookup('CAPTURED')))
        self.assertEqual(deleted, ['panel', 'circuit', 'panel', 'circuit'])
        self.assertIsNone(self.h.run("(EL:Get 'source-handle (EL:Get 'panel captured))"))
        self.assertIsNone(self.h.run("(EL:Get 'source-handle (EL:Get 'circuit captured))"))

    def test_probe_exception_still_deletes_temporary_block(self):
        deleted = []
        self.h.builtins.update({
            'SSGET': lambda *args: None,
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda app: 'doc',
            'VLA-GET-MODELSPACE': lambda doc: 'space',
            'VLAX-3D-POINT': lambda p: p,
            'VLA-INSERTBLOCK': lambda *args: 'panel',
            'VLAX-VLA-OBJECT->ENAME': lambda obj: obj,
            'VLA-DELETE': lambda obj: deleted.append(obj),
            'VLA-GET-ISDYNAMICBLOCK': lambda obj: (_ for _ in ()).throw(RuntimeError('bad property')),
        })
        self.assertIsNone(self.call('EL:CaptureFixedTemplate', self.cfg))
        self.assertEqual(deleted, ['panel'])

    def test_created_annotation_uses_text_layer_and_bylayer_appearance(self):
        assigned = {}
        self.h.builtins.update({
            'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda app: 'doc',
            'VLA-GET-LAYERS': lambda doc: 'layers',
            'VLA-ADD': lambda layers, name: assigned.update(created_layer=name),
            'VLAX-3D-POINT': lambda p: p,
            'VLA-ADDTEXT': lambda space, text, pos, height: assigned.update(text=text, pos=pos, initial_height=height) or 'text',
        })
        for key in ['Layer', 'StyleName', 'Color', 'Linetype', 'LinetypeScale', 'Lineweight',
                    'Height', 'Rotation', 'TextAlignmentPoint', 'Alignment', 'ScaleFactor', 'ObliqueAngle', 'Thickness', 'TextGenerationFlag']:
            self.h.builtins['VLA-PUT-' + key.upper()] = lambda obj, value, key=key: assigned.update({key: value})
        self.h.run("(setq row (list (cons 'annotation (EL:FixedText)) '(text . \"85W\") '(text-position 17063.0 -5938.0 0.0)))")
        self.h.run("(EL:CreateAnnotation nil row '((scale . 1.0) (rotation . 0.0)) \"EL-SYSTEM\")")
        for key, value in {'Layer': 'TEL_TEXT', 'StyleName': '_TEL_DIM', 'Height': 350.,
                           'ScaleFactor': .7, 'Alignment': 1, 'Rotation': 0., 'Color': 256,
                           'Linetype': 'ByLayer', 'Lineweight': -1, 'text': '85W'}.items():
            self.assertEqual(assigned[key], value)


if __name__ == '__main__':
    unittest.main()
