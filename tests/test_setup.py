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
        self.keywords = iter(())
        self.reals = iter(())
        self.unit = ''
        self.cancel_sample = False
        self.write_ok = True
        self.h.builtins.update({
            'EL:DRAWINGID': lambda: 'test.dwg',
            'EL:LOADCONFIG': lambda: self.saved or self.h.run('(EL:DefaultConfig "test.dwg")'),
            'EL:SAMPLE': self.sample,
            'EL:WRITEDATA': self.write,
            'GETSTRING': lambda *args: self.unit,
            'GETKWORD': lambda prompt: next(self.keywords),
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

    def run_setup(self, *keywords):
        self.keywords = iter(keywords)
        self.h.run('(c:ELSETUP)')

    def test_enter_saves_uncalibrated_draft_and_explains_next_step(self):
        self.run_setup(None, None)
        self.assertEqual(self.sampled, ['PANEL', 'WIRE', 'DEVICE'])
        self.assertEqual(self.get('units'), 'mm')
        self.assertFalse(truth(self.get('calibrated')))
        self.assertTrue(truth(self.h.call(Symbol('EL:PARAMSVALID'), [self.get('params')])))
        self.assertIn('草稿已保存', ''.join(self.messages))
        self.assertIn('ELGAPTEST', ''.join(self.messages))
        self.assertEqual(len(self.writes), 1)
        self.h.load_definitions(ROOT / 'src' / 'main.lsp')
        self.messages.clear()
        self.h.run('(c:ELTRACE)')
        self.assertIn('先运行 ELSETUP', ''.join(self.messages))

    def test_reopen_draft_reuses_samples_and_only_yes_confirms(self):
        self.run_setup(None, None)
        params = self.get('params')
        self.sampled.clear()
        self.messages.clear()
        self.run_setup(None, None, 'Yes')
        self.assertEqual(self.sampled, [])
        self.assertEqual(self.get('params'), params)
        self.assertTrue(truth(self.get('calibrated')))
        self.assertEqual(self.get('revision'), 2)
        self.assertIn('下一步：输入 ELSTAT', ''.join(self.messages))

    def test_reuse_keeps_custom_units_parameters_and_power_values(self):
        self.run_setup(None, None)
        self.h.frames[0]['TEST:CFG'] = self.saved
        self.saved = self.h.run('''
          (setq test:cfg (EL:Put 'units "cm" test:cfg))
          (setq test:cfg (EL:Put 'params (EL:Put 'Dmax 123.0 (EL:Get 'params test:cfg)) test:cfg))
          (EL:Put 'powers '(((identity "lamp" "definition" "state")
                            (category . lighting) (display . "灯具") (watts . 5))) test:cfg)''')
        powers = self.get('powers')
        self.sampled.clear()
        self.run_setup(None, None, 'No')
        self.assertEqual(self.sampled, [])
        self.assertEqual(self.get('units'), 'cm')
        self.assertEqual(self.get('Dmax', self.get('params')), 123.0)
        self.assertEqual(self.get('powers'), powers)
        self.assertFalse(truth(self.get('calibrated')))

    def test_resample_is_explicit(self):
        self.run_setup(None, None)
        self.sampled.clear()
        self.run_setup('Resample', None, 'Yes')
        self.assertEqual(self.sampled, ['PANEL', 'WIRE', 'DEVICE'])
        self.assertTrue(truth(self.get('calibrated')))

    def test_invalid_custom_parameters_do_not_save_or_confirm(self):
        self.reals = iter([-0.1, 0.1, 0.5, 0.01, 0.01, 20.0, 200.0])
        self.run_setup('Custom')
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
        self.run_setup(None, 'Yes')
        self.assertEqual(len(self.writes), 1)
        self.assertIsNone(self.saved)
        self.assertIn('配置未保存', ''.join(self.messages))
        self.assertNotIn('设置已确认并保存', ''.join(self.messages))


if __name__ == '__main__':
    unittest.main(verbosity=2)
