"""Date: 2026-10-20. Absolute LOAD without APPLOAD history; finite adapter only."""
from pathlib import Path
import sys
import unittest

from autolisp_host import Host, Symbol, truth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_cad2020 as builder


class FullEntryTests(unittest.TestCase):
    def fixture(self, fail=False, error=False):
        h = Host()
        h.load_definitions(ROOT / 'src/startup.lsp')
        # Native AutoLISP binds DEFUN symbols; this finite host stores functions separately.
        h.set('C:ELSTAT', True)
        calls = []
        h.builtins.update({
            'PRINC': lambda *args: None,
            'EL:PERFCALL': lambda stage, fn, args: h.call(fn, args or []),
            'EL:STARTUPFINDROOT': lambda marker: None,
            'EL:STARTUPREMEMBERROOT': lambda root, marker: root,
            'GETFILED': lambda *args: self.fail('automatic file picker'),
            'LOAD': lambda *args: self.fail('entry depends on another LOAD path'),
        })
        def embedded():
            calls.append('embedded')
            if error:
                raise RuntimeError('runtime write denied')
            return None if fail else f'C:/用户/运行目录/runtime-{builder.PACKAGE_NO}/'
        h.builtins['EL:STARTUPEMBEDDEDROOT'] = embedded
        h.builtins['OPEN-PANEL'] = lambda: calls.append('panel')
        startup = f'''
(defun c:ELSTAT () (OPEN-PANEL))
(setq *EL:MonitorLoadReady* (EL:StartupRoot "package-{builder.PACKAGE_NO}.marker"))
'''
        raw = builder.full_test_entry(startup)
        h.run(raw.decode('gb2312'))
        return h, calls

    def test_load_only_registers_then_command_uses_embedded_fallback(self):
        h, calls = self.fixture()
        self.assertEqual(calls, [])
        h.call(Symbol('C:' + builder.FULL_TEST_COMMAND), [])
        self.assertEqual(calls, ['embedded', 'panel'])
        self.assertIn(f'runtime-{builder.PACKAGE_NO}', h.lookup('*EL:ROOT*'))

    def test_failed_fallback_does_not_dispatch_stale_panel(self):
        for error in (False, True):
            h, calls = self.fixture(fail=True, error=error)
            h.set('*EL:MONITORLOADREADY*', True)
            h.call(Symbol('C:' + builder.FULL_TEST_COMMAND), [])
            self.assertEqual(calls, ['embedded'])
            self.assertFalse(truth(h.lookup('*EL:MONITORLOADREADY*')))

    def test_command_reinstalls_own_business_code_after_another_package(self):
        h, calls = self.fixture()
        h.run('(defun c:ELSTAT () (GETFILED "old" "" "" 0))')
        h.call(Symbol('C:' + builder.FULL_TEST_COMMAND), [])
        self.assertEqual(calls, ['embedded', 'panel'])


if __name__ == '__main__':
    unittest.main()
