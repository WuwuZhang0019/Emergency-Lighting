"""Setup prompt and persistence regressions. Date: 2026-10-08.

Runs the actual LISP control flow with scripted input; does not run CAD.
"""
import pathlib
import unittest

from autolisp_host import Host, Symbol, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for filename in ('common.lsp', 'config.lsp', 'statistics.lsp'):
            self.h.load_definitions(ROOT / 'src' / filename)
        self.saved = None
        self.writes = []
        self.sampled = []
        self.messages = []
        self.prompts = []
        self.keywords = iter(())
        self.integers = iter(())
        self.reals = iter(())
        self.cancel_sample = False
        self.write_ok = True
        self.h.builtins.update({
            'EL:DRAWINGID': lambda: 'test.dwg',
            'EL:LOADCONFIG': lambda: self.saved or self.h.run('(EL:DefaultConfig "test.dwg")'),
            'EL:SAMPLE': self.sample,
            'EL:WRITEDATA': self.write,
            'GETSTRING': lambda *args: self.fail('ELSETUP must not request a drawing unit'),
            'GETKWORD': lambda prompt: next(self.keywords),
            'GETINT': self.choice,
            'GETREAL': lambda prompt: next(self.reals),
            'INITGET': lambda *args: None,
            'VL-STRING-RIGHT-TRIM': lambda chars, text: text.rstrip(chars),
            'FINDFILE': lambda path: path if path.endswith(('.lsp', '.dcl')) else None,
            'VL-FILE-DIRECTORY-P': lambda path: True,
            'PRINC': lambda *args: self.messages.extend(args),
        })
        self.h.frames[0]['*EL:ROOT*'] = 'test-package/'

    def sample(self, cfg, role, prompt):
        self.sampled.append(role)
        if self.cancel_sample:
            return None
        cfg = self.h.call(Symbol('EL:PUT'), [Symbol(f'{role}-LAYERS'), [f'{role}-layer'], cfg])
        if role != 'WIRE':
            cfg = self.h.call(Symbol('EL:PUT'), [Symbol(f'{role}-NAMES'), [f'{role}-block'], cfg])
        return cfg

    def write(self, path, data):
        self.writes.append((path, data))
        if self.write_ok:
            self.saved = data
            return True
        return None

    def get(self, key, cfg=None):
        return self.h.call(Symbol('EL:GET'), [Symbol(key.upper()), cfg or self.saved])

    def choice(self, prompt):
        self.prompts.append(prompt)
        return next(self.integers)

    def run_setup(self, *choices, reuse=None):
        self.keywords = iter([reuse])
        self.integers = iter(choices)
        self.h.run('(c:ELSETUP)')

    def test_enter_saves_uncalibrated_draft_and_explains_next_step(self):
        self.run_setup(None, None)
        self.assertEqual(self.sampled, ['PANEL', 'WIRE', 'DEVICE'])
        self.assertEqual(self.get('units'), 'mm')
        self.assertIn('单位固定为 mm', ''.join(self.messages))
        self.assertIn('回车直接使用', self.prompts[0])
        self.assertIn('回车保存草稿', self.prompts[1])
        self.assertFalse(truth(self.get('calibrated')))
        self.assertTrue(truth(self.h.call(Symbol('EL:PARAMSVALID'), [self.get('params')])))
        self.assertIn('草稿已保存', ''.join(self.messages))
        self.assertIn('ELGAPTEST', ''.join(self.messages))
        self.assertEqual(len(self.writes), 1)
        self.h.load_definitions(ROOT / 'src' / 'main.lsp')
        self.messages.clear()
        self.h.run('(c:ELTRACE)')
        self.assertIn('先运行 ELSETUP', ''.join(self.messages))

    def test_reopen_draft_reuses_samples_and_only_explicit_choice_confirms(self):
        self.run_setup(None, None)
        params = self.get('params')
        self.sampled.clear()
        self.messages.clear()
        self.run_setup(None, 1)
        self.assertEqual(self.sampled, [])
        self.assertEqual(self.get('params'), params)
        self.assertTrue(truth(self.get('calibrated')))
        self.assertEqual(self.get('revision'), 2)
        self.assertIn('下一步：输入 ELSTAT', ''.join(self.messages))

    def test_fixed_mm_reuses_custom_parameters_and_power_values(self):
        self.run_setup(None, None)
        self.h.frames[0]['TEST:CFG'] = self.saved
        self.saved = self.h.run('''
          (setq test:cfg (EL:Put 'units "cm" test:cfg))
          (setq test:cfg (EL:Put 'params (EL:Put 'Dmax 123.0 (EL:Get 'params test:cfg)) test:cfg))
          (EL:Put 'powers '(((identity "lamp" "definition" "state")
                            (category . lighting) (display . "灯具") (watts . 5))) test:cfg)''')
        powers = self.get('powers')
        self.sampled.clear()
        self.run_setup(None, 2)
        self.assertEqual(self.sampled, [])
        self.assertEqual(self.get('units'), 'mm')
        self.assertEqual(self.get('Dmax', self.get('params')), 123.0)
        self.assertEqual(self.get('powers'), powers)
        self.assertFalse(truth(self.get('calibrated')))

    def test_resample_is_explicit(self):
        self.run_setup(None, None)
        self.sampled.clear()
        self.run_setup(None, 1, reuse='Resample')
        self.assertEqual(self.sampled, ['PANEL', 'WIRE', 'DEVICE'])
        self.assertTrue(truth(self.get('calibrated')))

    def test_invalid_custom_parameters_do_not_save_or_confirm(self):
        self.reals = iter([-0.1, 0.1, 2000.0])
        self.run_setup(2)
        self.assertEqual(self.writes, [])
        self.assertIsNone(self.saved)
        self.assertIn('参数范围无效，未保存', ''.join(self.messages))

    def test_missing_sample_does_not_save(self):
        self.cancel_sample = True
        self.run_setup()
        self.assertEqual(self.writes, [])
        self.assertIn('采样未完成', ''.join(self.messages))

    def test_write_failure_never_reports_success(self):
        self.write_ok = False
        self.run_setup(None, 1)
        self.assertEqual(len(self.writes), 1)
        self.assertIsNone(self.saved)
        self.assertIn('配置未保存', ''.join(self.messages))
        self.assertNotIn('设置已确认并保存', ''.join(self.messages))

    def test_confirmed_unchanged_setup_does_not_ask_for_confirmation_again(self):
        self.run_setup(None, 1)
        self.prompts.clear()
        self.messages.clear()
        self.run_setup(None)
        self.assertEqual(len(self.prompts), 1)
        self.assertTrue(truth(self.get('calibrated')))
        self.assertIn('沿用已核对的设置', ''.join(self.messages))

    def test_editing_without_value_changes_keeps_existing_confirmation(self):
        self.run_setup(None, 1)
        params = self.get('params')
        self.prompts.clear()
        self.reals = iter([None] * 3)
        self.run_setup(2)
        self.assertEqual(self.get('params'), params)
        self.assertEqual(len(self.prompts), 1)
        self.assertTrue(truth(self.get('calibrated')))

    def test_changed_parameter_requires_confirmation_and_can_save_draft(self):
        self.run_setup(None, 1)
        self.prompts.clear()
        self.reals = iter([None] * 2 + [123.0])
        self.run_setup(2, None)
        self.assertEqual(self.get('Dmax', self.get('params')), 123.0)
        self.assertEqual(len(self.prompts), 2)
        self.assertFalse(truth(self.get('calibrated')))

    def test_resampling_confirmed_config_requires_new_confirmation(self):
        self.run_setup(None, 1)
        self.run_setup(None, None, reuse='Resample')
        self.assertFalse(truth(self.get('calibrated')))

    def test_choices_outside_one_or_two_reprompt_without_saving_early(self):
        self.run_setup(3, None, 9, None)
        self.assertEqual(len(self.prompts), 4)
        self.assertEqual(len(self.writes), 1)
        self.assertFalse(truth(self.get('calibrated')))
        self.assertIn('请输入 1 或 2', ''.join(self.messages))

    def test_changed_unit_label_requires_confirmation_but_never_unit_input(self):
        self.run_setup(None, 1)
        self.h.frames[0]['TEST:CFG'] = self.saved
        self.saved = self.h.run('(EL:Put \'units "cm" test:cfg)')
        self.prompts.clear()
        self.run_setup(None, None)
        self.assertEqual(self.get('units'), 'mm')
        self.assertEqual(len(self.prompts), 2)
        self.assertFalse(truth(self.get('calibrated')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
