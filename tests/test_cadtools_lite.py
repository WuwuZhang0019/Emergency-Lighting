"""Date: 2026-10-16. In-memory runtime/loader checks; no delivery or native CAD."""
from pathlib import Path
import posixpath
import sys
import unittest
from unittest.mock import patch

from autolisp_host import Host, Symbol, parse, truth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_cad2020 as full
import cadtools_lite as lite


def definitions(text):
    return [form for form in parse(text)
            if isinstance(form, list) and form[0] == 'DEFUN']


class LiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = lite.runtime_files()

    def test_runtime_manifest_encoding_and_resource_fidelity(self):
        self.assertLess(len(self.files), 145)
        self.assertLess(sum(map(len, self.files.values())), 3 * 1024 * 1024)
        self.assertEqual([p for p in self.files if p.endswith('.md')], ['使用说明.md'])
        self.assertFalse(any(p.startswith(('tests/', 'docs/', 'config/', 'output/')) for p in self.files))
        for absent in ('START-CAD2020.lsp', full.UPDATE_NAME, 'CCKK.lsp', 'src/diagnostic-bundle.ps1'):
            self.assertNotIn(absent, self.files)
        for name, data in self.files.items():
            if name.endswith(('.lsp', '.dcl')):
                self.assertEqual(data.decode('gb2312').encode('gb2312'), data)
                self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
                if name.endswith('.lsp'):
                    parse(data.decode('gb2312'))
            elif name.startswith(('assets/', 'templates/')):
                self.assertEqual(data, (ROOT / name).read_bytes())

    def test_every_public_command_is_retained(self):
        def commands(text):
            return {form[1] for form in definitions(text) if str(form[1]).startswith('C:')}
        source_commands = set().union(*(commands(p.read_text(encoding='utf-8'))
                                       for p in (ROOT / 'src').glob('*.lsp')))
        lite_commands = set().union(*(commands(data.decode('gb2312'))
                                     for name, data in self.files.items() if name.endswith('.lsp')))
        self.assertEqual(source_commands, lite_commands)

    def test_version_tracks_full_and_diagnostics_remain_embedded(self):
        with patch.object(full, 'VERSION', '9.8.7'):
            files = lite.runtime_files()
        self.assertIn('lite-v9.8.7.marker', files)
        self.assertIn('lite-v9.8.7', files['src/load.lsp'].decode('gb2312'))
        self.assertIn('版本：lite-v9.8.7', files['使用说明.md'].decode('utf-8'))
        h = Host()
        for form in definitions(self.files['src/common.lsp'].decode('gb2312')):
            h.evaluate(form)
        for form in definitions(self.files['src/diagram-commands.lsp'].decode('gb2312')):
            h.evaluate(form)
        self.assertEqual(h.run('(EL:DiagnosticScriptText)'),
                         (ROOT / 'src/diagnostic-bundle.ps1').read_text(encoding='utf-8'))

    def fixture(self, explicit=True):
        h = Host()
        root = '/Program Files/CADTools/Emergency-Lighting/'
        virtual = {posixpath.normpath(root + name): data for name, data in self.files.items()}
        dirs, loaded, messages = {'/Users/test'}, [], []
        install_dirs = {posixpath.dirname(path) for path in virtual}
        env = {'LOCALAPPDATA': '/Users/test'}
        def load(path):
            loaded.append(path)
            for form in definitions(virtual[posixpath.normpath(path)].decode('gb2312')):
                h.evaluate(form)
            return True
        def mkdir(path):
            self.assertTrue(path.startswith('/Users/test/'))
            dirs.add(path.rstrip('/'))
            return True
        h.builtins.update({
            'GETVAR': lambda key: {'MILLISECS': 0, 'CPROFILE': 'test'}[key],
            'VL-LOAD-COM': lambda: None,
            'VL-STRING-RIGHT-TRIM': lambda chars, value: value.rstrip(chars),
            'VL-FILENAME-DIRECTORY': posixpath.dirname,
            'FINDFILE': lambda path: path if posixpath.normpath(path) in virtual else None,
            'VL-FILE-DIRECTORY-P': lambda path: posixpath.normpath(path) in dirs | install_dirs,
            'VL-MKDIR': mkdir,
            'GETENV': env.get,
            'SETENV': lambda key, value: env.__setitem__(key, value) or value,
            'VLAX-PRODUCT-KEY': lambda: 'Software/AutoCAD',
            'VL-REGISTRY-READ': lambda key, name: root + 'src/load.lsp' if name == 'MainDialog' else None,
            'LOAD': load,
            'PRINC': lambda *args: messages.extend(args),
            'EL:MONITORLOADBEGIN': lambda *args: None,
            'EL:MONITORLOADEND': lambda *args: None,
            'EL:PERFBEGIN': lambda *args: 1,
            'EL:PERFEND': lambda *args: None,
            'EL:PERFCALL': lambda label, fn, args: h.call(fn, args or []),
            'EL:DLDEFAULTSTARTUP': lambda: True,
            'EL:CLEARPICKHIGHLIGHTS': lambda: None,
        })
        if explicit:
            h.set('*EL:CADTOOLSROOT*', root)
        loader = parse(self.files['src/load.lsp'].decode('gb2312'))
        for form in loader[:-2]:
            h.evaluate(form)
        return h, root, virtual, dirs, loaded, messages, env

    def test_loader_order_readonly_install_and_persistent_data_paths(self):
        h, root, virtual, dirs, loaded, messages, env = self.fixture()
        self.assertTrue(truth(h.run('(EL:LiteLoad)')))
        self.assertEqual(loaded, [root + f'src/{m}.lsp' for m in (*full.MODULES, 'batch-number')])
        data_root = '/Users/test/Emergency-Lighting/CADTools/'
        self.assertEqual(h.lookup('*EL:LITEDATAROOT*'), data_root)
        self.assertTrue(truth(h.run('(EL:RootValid *EL:Root*)')))
        self.assertTrue(h.run('(EL:ConfigPath "drawing")').startswith(data_root + 'config/'))
        self.assertEqual(h.run('(EL:DLDefaultSource)'), root + 'assets/default-device-library/')
        self.assertEqual(h.run('(EL:DLRoot)'), '/Users/test/Emergency-Lighting/device-library/')
        h.set('*EL:DLROOT*', '/Users/test/custom-library/')
        for name, data in self.files.items():
            if name.endswith('.lsp'):
                text = data.decode('gb2312')
                self.assertNotIn('(strcat *EL:Root* "config/', text)
                self.assertNotIn('(strcat *EL:Root* "output', text)
        previous_dirs = dirs.copy()
        self.assertTrue(truth(h.run('(EL:LiteLoad)')))
        self.assertEqual(dirs, previous_dirs)
        self.assertEqual(h.lookup('*EL:LITEDATAROOT*'), data_root)
        self.assertEqual(h.run('(EL:DLRoot)'), '/Users/test/custom-library/')

    def test_appload_can_locate_the_same_complete_install(self):
        h, root, *_ = self.fixture(explicit=False)
        self.assertEqual(h.run('(EL:LiteFindRoot)'), root + 'src/../')
        self.assertTrue(truth(h.run('(EL:LiteLoad)')))

    def test_missing_asset_stops_before_loading_or_creating_data(self):
        h, root, virtual, dirs, loaded, messages, env = self.fixture()
        asset = next(name for name in virtual if name.endswith('block.dwg'))
        del virtual[asset]
        self.assertFalse(truth(h.run('(EL:LiteLoad)')))
        self.assertEqual(loaded, [])
        self.assertEqual(dirs, {'/Users/test'})
        self.assertIsNone(h.lookup('*EL:ROOT*'))
        self.assertIn('运行文件不完整', ''.join(messages))

    def test_wrong_explicit_root_does_not_fall_back_to_appload(self):
        h, *_ = self.fixture()
        h.set('*EL:CADTOOLSROOT*', '/broken/')
        self.assertFalse(truth(h.run('(EL:LiteFindRoot)')))

    def test_missing_localappdata_and_module_error_are_reported(self):
        h, root, virtual, dirs, loaded, messages, env = self.fixture()
        env.clear()
        self.assertFalse(truth(h.run('(EL:LiteLoad)')))
        self.assertEqual(loaded, [])
        self.assertIn('LOCALAPPDATA', ''.join(messages))
        env['LOCALAPPDATA'] = '/Users/test'
        def fail(path):
            raise RuntimeError('load denied')
        h.builtins['LOAD'] = fail
        self.assertFalse(truth(h.run('(EL:LiteLoad)')))
        self.assertIsNone(h.lookup('*EL:ROOT*'))
        self.assertFalse(truth(h.lookup('*EL:MONITORLOADREADY*')))
        self.assertIn('load denied', ''.join(messages))


if __name__ == '__main__':
    unittest.main()
