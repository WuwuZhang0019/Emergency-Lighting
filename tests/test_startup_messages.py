"""Date: 2026-10-15. Startup failure and final command hint; no package build."""
import importlib.util
from unittest.mock import patch
import unittest

from autolisp_host import Symbol, truth
import test_root_init as roots

ROOT = roots.ROOT
spec = importlib.util.spec_from_file_location('startup_message_builder', ROOT / 'tools/build_cad2020.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class StartupMessageTests(roots.RootFixture):
    def setUp(self):
        super().setUp()
        self.h.load_definitions(ROOT / 'src/startup.lsp')

    def test_success_command_hint_is_after_all_loading_reports(self):
        self.h.frames[0]['*EL:ROOT*'] = self.root
        self.h.frames[0]['*EL:MONITORLOADREADY*'] = True
        self.h.run('(EL:MonitorLoadBegin 0)')
        self.h.run(builder.LOAD_COMPLETION)
        self.assertTrue(any('全过程耗时文档' in line for line in self.messages))
        self.assertTrue(self.messages[-1].startswith('\n启动命令：输入 ELSTAT'))
        self.assertFalse(truth(self.h.lookup('*EL:PERFACTIVE*')))

    def fail_startup(self):
        self.h.builtins['EL:STARTUPFINDROOT'] = lambda marker: None
        def failed():
            self.h.set('*EL:STARTUPERROR*', 'C:/runtime-143/src/diagnostic-bundle.ps1 [SAVE_TO_FILE] : access denied')
            return None
        self.h.builtins['EL:STARTUPEMBEDDEDROOT'] = failed
        self.assertFalse(truth(self.h.run('(EL:StartupRoot "package-143.marker")')))

    def test_failed_startup_then_repeated_commands_never_reopen_picker(self):
        self.fail_startup()
        self.h.run('(EL:EnsureRoot) (EL:EnsureRoot)')
        self.assertEqual(self.dialogs, [])
        self.assertIsNone(self.h.lookup('*EL:ROOT*'))
        self.assertIn('[SAVE_TO_FILE]', ''.join(self.messages))
        self.assertIn('C:\\runtime-143\\src\\diagnostic-bundle.ps1', ''.join(self.messages))

    def test_failure_footer_does_not_suggest_starting_statistics(self):
        self.h.run('(EL:MonitorLoadBegin 0)')
        self.fail_startup()
        self.h.run(builder.LOAD_COMPLETION)
        self.assertIn('启动未完成', self.messages[-1])
        self.assertNotIn('输入 ELSTAT', self.messages[-1])

    def test_embedded_helper_does_not_require_ps1_file_or_extract_it(self):
        (self.package / 'src/diagnostic-bundle.ps1').unlink()
        self.assertTrue(truth(self.h.run('(EL:RootValid "' + self.root + '")')))
        self.h.run(builder.diagnostic_script_definition())
        self.assertEqual(self.h.run('(EL:DiagnosticScriptText)'),
                         (ROOT / 'src/diagnostic-bundle.ps1').read_text(encoding='utf-8'))
        with patch.object(builder, 'DEST', self.package):
            embedded = builder.embedded_resources()
        self.assertNotIn('(strcat root "src/diagnostic-bundle.ps1")', embedded)

    def test_manual_elroot_can_recover_after_automatic_failure(self):
        self.fail_startup()
        (self.package / 'package-143.marker').write_text('143', encoding='ascii')
        self.selections = iter([self.selected])
        self.h.run('(c:ELROOT)')
        self.assertEqual(len(self.dialogs), 1)
        self.assertTrue(truth(self.h.run('(EL:EnsureRoot)')))
        self.assertEqual(len(self.dialogs), 1)


if __name__ == '__main__':
    unittest.main()
