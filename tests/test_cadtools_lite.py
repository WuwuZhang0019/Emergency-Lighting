"""Date: 2026-10-20. In-memory runtime/loader checks; no delivery or native CAD."""
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
        self.assertLess(sum(map(len, self.files.values())), 5 * 1024 * 1024)
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
        # ELROOT belongs to the guarded loader body, evaluated only after validation.
        h, *_ = self.fixture()
        self.assertTrue(truth(h.run('(EL:LiteLoad)')))
        self.assertTrue(source_commands.issubset(h.functions))
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
            self.fail(f'entry must not LOAD another executable: {path}')
        def begin(tick):
            loaded.append('common')
        def perf_begin(label):
            if label == 'LOAD_MODULE':
                loaded.append(h.lookup('*EL:MONITORLABEL*').removesuffix('.lsp'))
            return 1
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
            'EL:MONITORLOADBEGIN': begin,
            'EL:MONITORLOADEND': lambda *args: None,
            'EL:PERFBEGIN': perf_begin,
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
        self.assertEqual(loaded, [*full.MODULES, 'batch-number'])
        self.assertTrue(h.lookup('*EL:SPLITSTORAGELOADED*'))
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

    def test_failed_first_start_still_registers_manual_root_recovery(self):
        h, root, virtual, dirs, loaded, messages, env = self.fixture()
        h.set('*EL:CADTOOLSROOT*', '/broken/')
        self.assertFalse(truth(h.run('(EL:LiteLoad)')))
        self.assertTrue(Symbol('C:ELROOT') in h.functions)
        h.builtins['GETFILED'] = lambda *args: root + 'src/load.lsp'
        h.run('(C:ELROOT)')
        self.assertTrue(truth(h.lookup('*EL:MONITORLOADREADY*')))
        self.assertEqual(h.lookup('*EL:ROOT*'), root + 'src/../')

    def test_registry_error_does_not_hide_a_valid_remembered_install(self):
        h, root, virtual, dirs, loaded, messages, env = self.fixture(explicit=False)
        env['EL_CADTOOLS_' + lite.version()] = root
        def unavailable(*args):
            raise RuntimeError('registry unavailable')
        h.builtins['VL-REGISTRY-READ'] = unavailable
        self.assertTrue(truth(h.run('(EL:LiteLoad)')), ''.join(messages))
        self.assertEqual(h.lookup('*EL:ROOT*'), root)

    def test_src_only_support_path_finds_its_own_marked_install(self):
        h, root, virtual, dirs, loaded, messages, env = self.fixture(explicit=False)
        original_find = h.builtins['FINDFILE']
        h.builtins['VL-REGISTRY-READ'] = lambda *args: '/old-or-missing/'
        h.builtins['FINDFILE'] = lambda path: (root + 'src/load.lsp'
            if path == 'load.lsp' else original_find(path))
        self.assertTrue(truth(h.run('(EL:LiteLoad)')), ''.join(messages))
        self.assertEqual(h.lookup('*EL:ROOT*'), root + 'src/../')

    def test_preflight_failure_after_reload_does_not_restore_an_old_error_handler(self):
        h, *_ = self.fixture()
        self.assertTrue(truth(h.run('(EL:LiteLoad)')))
        h.builtins.pop('EL:MONITORLOADEND')
        h.builtins['EL:PERFFINISH'] = lambda *args: None
        h.set('*EL:MONITOROLDERROR*', Symbol('OLD-HANDLER'))
        h.set('*ERROR*', Symbol('CURRENT-HANDLER'))
        h.set('*EL:CADTOOLSROOT*', '/broken/')
        self.assertFalse(truth(h.run('(EL:LiteLoad)')))
        self.assertEqual(h.lookup('*ERROR*'), Symbol('CURRENT-HANDLER'))

    def test_missing_localappdata_and_module_error_are_reported(self):
        h, root, virtual, dirs, loaded, messages, env = self.fixture()
        env.clear()
        self.assertFalse(truth(h.run('(EL:LiteLoad)')))
        self.assertEqual(loaded, [])
        self.assertIn('LOCALAPPDATA', ''.join(messages))
        env['LOCALAPPDATA'] = '/Users/test'
        def fail():
            raise RuntimeError('module initialization failed')
        h.builtins['EL:LITEDEFINEMODULES'] = fail
        self.assertFalse(truth(h.run('(EL:LiteLoad)')))
        self.assertIsNone(h.lookup('*EL:ROOT*'))
        self.assertFalse(truth(h.lookup('*EL:MONITORLOADREADY*')))
        self.assertIn('module initialization failed', ''.join(messages))

    def test_embedded_modules_keep_exact_shared_text_and_have_no_nested_load(self):
        loader = self.files['src/load.lsp'].decode('gb2312')
        def calls(form):
            if isinstance(form, list):
                if form and form[0] == 'LOAD':
                    yield form
                for part in form:
                    yield from calls(part)
        self.assertEqual(list(calls(parse(loader))), [])
        last = -1
        for module in (*full.MODULES, 'batch-number'):
            text = self.files[f'src/{module}.lsp'].decode('gb2312')
            position = loader.index(text)
            self.assertGreater(position, last)
            last = position

    def test_lite_entry_replays_original_touching_device_and_downstream_wire_chain(self):
        from actual_contact_fixture import ActualContactFixture
        h, *_ = self.fixture()
        self.assertTrue(truth(h.run('(EL:LiteLoad)')))
        f = ActualContactFixture(host=h)
        network = f.build_case('tiny_device_chain')
        self.assertEqual({f.get('id', b) for b in f.get('devices', network)},
                         {'F099', '84B8', '8267'})
        self.assertEqual(set(f.get('wire-ids', network)), {'F097', 'F159', 'F15A'})
        result = f.split(network)
        self.assertTrue(truth(f.get('complete', result)))
        self.assertEqual(set(f.get('devices', f.get('circuits', result)[0])),
                         {'F099', '84B8', '8267'})


if __name__ == '__main__':
    unittest.main()
