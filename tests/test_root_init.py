"""Root/config and packaged-update regressions. Date: 2026-10-09.

Executes actual LISP with file/input adapters; does not start AutoCAD.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from autolisp_host import Host, Pair, Symbol, parse, quoted, truth

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK_ROOT = ROOT / 'output' / 'cad2020-root-check'
MODULES = ('common', 'config', 'geometry', 'topology', 'statistics', 'generation', 'main', 'simple', 'fixed', 'panel', 'diagram-store', 'diagram-update', 'diagram-commands')


def lisp_data(value):
    """Serialize data for the file adapter using AutoLISP's readable syntax."""
    if value is None or value is False:
        return 'nil'
    if value is True:
        return 'T'
    if isinstance(value, Symbol):
        return str(value)
    if isinstance(value, Pair):
        return f'({lisp_data(value.car)} . {lisp_data(value.cdr)})'
    if isinstance(value, list):
        return '(' + ' '.join(map(lisp_data, value)) + ')'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


class RootFixture(unittest.TestCase):
    def test_old_ui_directory_requires_complete_new_package(self):
        marker = self.package / 'ui/box-ui-011.marker'
        marker.unlink()
        self.assertFalse(truth(self.h.call(Symbol('EL:ROOTVALID'), [self.root])))

    def setUp(self):
        self.assertTrue(CHECK_ROOT.resolve().is_relative_to(ROOT))
        CHECK_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=CHECK_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.package = pathlib.Path(self.temp.name) / '已有包'
        shutil.copytree(ROOT / 'src', self.package / 'src')
        shutil.copytree(ROOT / 'ui', self.package / 'ui')
        for folder in ('config', 'output', 'templates'):
            (self.package / folder).mkdir()
        self.root = self.package.as_posix() + '/'
        self.selected = (self.package / 'src/load.lsp').as_posix()
        self.h = Host()
        for module in MODULES:
            self.h.load_definitions(ROOT / 'src' / f'{module}.lsp')
        self.messages = []
        self.selections = iter(())
        self.dialogs = []
        self.picks = []
        self.opens = []
        self.drawing = {'DWGTITLED': 1, 'DWGPREFIX': 'C:/drawings/',
                        'DWGNAME': '照明.dwg', 'CDATE': 20261008.1}
        self.h.builtins.update({
            'GETVAR': lambda name: self.drawing[name],
            'STRCAT': self.strcat,
            'VL-STRING-RIGHT-TRIM': lambda chars, text: text.rstrip(chars),
            'FINDFILE': lambda path: path if pathlib.Path(path).is_file() else None,
            'VL-FILE-DIRECTORY-P': lambda path: pathlib.Path(path).is_dir(),
            'VL-FILENAME-DIRECTORY': lambda path: pathlib.Path(path).parent.as_posix(),
            'VL-FILENAME-BASE': lambda path: pathlib.Path(path).stem,
            'VL-FILENAME-EXTENSION': lambda path: pathlib.Path(path).suffix or None,
            'GETFILED': self.select,
            'OPEN': self.open_file,
            'READ-LINE': self.read_line,
            'READ': lambda text: quoted(parse(text)[0]),
            'WRITE-LINE': lambda line, file: file.write(line + '\n'),
            'CLOSE': lambda file: file.close(),
            'VL-PRIN1-TO-STRING': lisp_data,
            'VL-FILE-DELETE': lambda path: pathlib.Path(path).unlink() or True,
            'VL-FILE-RENAME': lambda src, dst: pathlib.Path(src).rename(dst) or True,
            'VL-FILE-COPY': lambda src, dst: shutil.copyfile(src, dst) and True,
            'PRINC': lambda *args: self.messages.extend(args),
            'ENTSEL': lambda prompt: self.picks.append(prompt) and None,
            'TBLSEARCH': lambda *args: True,
            'VL-LOAD-COM': lambda: None,
        })

    @staticmethod
    def strcat(*parts):
        # Fail with CAD's reported error if a nil path escapes the guards.
        if any(part is None for part in parts):
            raise TypeError('bad argument type: stringp: nil')
        return ''.join(parts)

    def select(self, *args):
        self.dialogs.append(args)
        return next(self.selections)

    def open_file(self, path, mode, *encoding):
        self.opens.append((path, mode, encoding))
        return open(path, mode, encoding='utf-8' if encoding else 'gb2312')

    @staticmethod
    def read_line(file):
        line = file.readline()
        return line.rstrip('\r\n') if line else None

    def get(self, key, cfg):
        return self.h.call(Symbol('EL:GET'), [Symbol(key.upper()), cfg])

    def config_path(self):
        return pathlib.Path(self.h.run('(EL:ConfigPath (EL:DrawingID))'))

    def calibrated_config(self):
        return self.h.run('''
          (setq test:cfg (EL:DefaultConfig (EL:DrawingID)))
          (setq test:cfg (EL:Put 'units "mm" test:cfg))
          (setq test:cfg (EL:Put 'params (EL:SuggestedParams) test:cfg))
          (setq test:cfg (EL:Put 'calibrated T test:cfg))
          (setq test:cfg (EL:Put 'panel-layers '("P") test:cfg))
          (setq test:cfg (EL:Put 'wire-layers '("W") test:cfg))
          (setq test:cfg (EL:Put 'device-layers '("D") test:cfg))
          (setq test:cfg (EL:Put 'panel-names '("BOX") test:cfg))
          (EL:Put 'device-names '("LAMP") test:cfg)''')


class RootInitTests(RootFixture):
    def test_missing_post_stat_ui_marker_rejects_old_dialog(self):
        (self.package / 'ui/diagram-ui-044.marker').unlink()
        self.assertFalse(truth(self.h.call(Symbol('EL:ROOTVALID'), [self.root])))

    def test_missing_root_is_initialized_before_config_path_is_used(self):
        self.selections = iter([self.selected])
        cfg = self.h.run('(EL:LoadConfig)')
        self.assertTrue(truth(cfg))
        self.assertEqual(self.get('drawing', cfg), 'C:/DRAWINGS/照明.DWG')
        self.assertEqual(len(self.dialogs), 1)
        self.assertEqual(pathlib.Path(self.h.lookup('*EL:ROOT*')).resolve(), self.package)
        self.assertEqual(self.config_path().parent.resolve(), self.package / 'config')
        self.assertEqual(self.opens, [])

    def test_empty_wrong_type_and_deleted_roots_request_relocation(self):
        for root in ('', 42, Symbol('BROKEN'), (self.package / 'gone').as_posix()):
            with self.subTest(root=root):
                self.h.frames[0]['*EL:ROOT*'] = root
                self.selections = iter([self.selected])
                self.assertTrue(truth(self.h.run('(EL:LoadConfig)')))
                self.assertEqual(pathlib.Path(self.h.lookup('*EL:ROOT*')).resolve(), self.package)
        self.assertEqual(len(self.dialogs), 4)

    def test_valid_root_with_or_without_trailing_separator_keeps_saved_config(self):
        self.h.frames[0]['*EL:ROOT*'] = self.root
        cfg = self.calibrated_config()
        self.h.frames[0]['TEST:CFG'] = cfg
        saved = self.h.run('(EL:SaveConfig test:cfg)')
        self.assertTrue(truth(saved))
        for root in (self.root, self.root.rstrip('/'), self.root.replace('/', '\\')):
            with self.subTest(root=root):
                self.h.frames[0]['*EL:ROOT*'] = root
                self.assertEqual(self.h.run('(EL:LoadConfig)'), saved)
        self.assertEqual(self.dialogs, [])
        self.assertEqual(self.get('revision', saved), 1)
        self.assertEqual(self.get('units', saved), 'mm')
        self.assertTrue(truth(self.get('calibrated', saved)))

    def test_config_path_rejects_nil_or_non_string_root_and_drawing_id(self):
        for root, drawing in ((None, 'test.dwg'), (42, 'test.dwg'), ('', 'test.dwg'),
                              (self.root, None), (self.root, 42), (self.root, '')):
            with self.subTest(root=root, drawing=drawing):
                self.h.frames[0]['*EL:ROOT*'] = root
                self.h.frames[0]['TEST:ID'] = drawing
                self.assertIsNone(self.h.run('(EL:ConfigPath test:id)'))
        self.assertEqual(self.dialogs, [])

    def test_cancelled_setup_does_not_reprompt_backup_or_create_config(self):
        self.h.frames[0]['*EL:ROOT*'] = str(self.package / 'gone')
        self.selections = iter([None])
        self.h.run('(c:ELSETUP)')
        self.assertEqual(len(self.dialogs), 1)
        self.assertEqual(self.picks, [])
        self.assertEqual(self.opens, [])
        self.assertEqual(list((self.package / 'config').iterdir()), [])
        self.assertIsNone(self.h.lookup('*EL:ROOT*'))
        self.assertIn('本次操作已停止', ''.join(self.messages))

    def test_cancelled_setup_config_does_not_build_invalid_backup_path(self):
        self.selections = iter([None])
        self.assertIsNone(self.h.run('(EL:SetupConfig)'))
        self.assertEqual(len(self.dialogs), 1)
        self.assertEqual(self.opens, [])

    def test_save_initializes_missing_root_and_can_read_back_the_config(self):
        self.h.frames[0]['TEST:CFG'] = self.calibrated_config()
        self.selections = iter([self.selected])
        saved = self.h.run('(EL:SaveConfig test:cfg)')
        self.assertTrue(truth(saved))
        self.assertEqual(self.get('revision', saved), 1)
        self.assertEqual(self.h.run('(EL:LoadConfig)'), saved)
        self.assertEqual(len(self.dialogs), 1)

    def test_cancelled_save_does_not_write_config_or_report_success(self):
        self.h.frames[0]['TEST:CFG'] = self.calibrated_config()
        self.selections = iter([None])
        self.assertIsNone(self.h.run('(EL:SaveConfig test:cfg)'))
        self.assertEqual(self.opens, [])
        self.assertEqual(list((self.package / 'config').iterdir()), [])
        self.assertIn('配置未保存', ''.join(self.messages))

    def test_wrong_file_and_incomplete_package_are_not_accepted(self):
        for filename in ('common.lsp', 'load', 'load.txt'):
            with self.subTest(filename=filename):
                self.selections = iter([(self.package / 'src' / filename).as_posix()])
                self.assertIsNone(self.h.run('(EL:LoadConfig)'))
                self.assertIsNone(self.h.lookup('*EL:ROOT*'))
        (self.package / 'ui/power.dcl').unlink()
        self.selections = iter([self.selected])
        self.assertIsNone(self.h.run('(EL:LoadConfig)'))
        self.assertIsNone(self.h.lookup('*EL:ROOT*'))
        self.assertEqual(self.opens, [])

    def test_unsaved_drawing_stops_before_directory_selection(self):
        self.drawing['DWGTITLED'] = 0
        self.assertIsNone(self.h.run('(EL:LoadConfig)'))
        self.assertEqual(self.dialogs, [])
        self.assertIn('请先保存 DWG', ''.join(self.messages))

    def test_invalid_config_backup_still_preserves_previous_data(self):
        self.h.frames[0]['*EL:ROOT*'] = self.root
        path = self.config_path()
        path.write_text('(invalid)', encoding='utf-8')
        self.assertTrue(truth(self.h.run('(EL:SetupConfig)')))
        backups = list(path.parent.glob(path.name + '.invalid-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), '(invalid)')
        self.assertEqual(path.read_text(encoding='utf-8'), '(invalid)')
        self.assertEqual(self.dialogs, [])


class PackagedUpdateTests(RootFixture):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('build_cad2020', ROOT / 'tools/build_cad2020.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)
        assert CHECK_ROOT.resolve().is_relative_to(ROOT)
        CHECK_ROOT.mkdir(parents=True, exist_ok=True)
        cls.build_temp = tempfile.TemporaryDirectory(dir=CHECK_ROOT)
        cls.addClassCleanup(cls.build_temp.cleanup)
        cls.built = pathlib.Path(cls.build_temp.name) / cls.builder.NAME
        with patch.object(cls.builder, 'DEST', cls.built), contextlib.redirect_stdout(io.StringIO()):
            cls.builder.build()
        cls.update = (cls.built / cls.builder.UPDATE_NAME).read_bytes().decode('gb2312')

    def test_standalone_update_initializes_root_then_setup_reaches_actual_pick(self):
        # A fresh drawing/session has no definitions and no *EL:Root*.
        self.h.functions.clear()
        self.selections = iter([(self.built / 'src/load.lsp').as_posix()])
        self.h.run(self.update)
        self.assertIn('目录已确认', ''.join(self.messages))
        self.assertEqual(len(self.dialogs), 1)
        self.h.run('(c:ELSETUP)')
        self.assertEqual(len(self.dialogs), 1)
        self.assertEqual(len(self.picks), 1)
        self.assertIn('拾取配电箱图块样本', self.picks[0])
        self.assertEqual(self.opens, [])

    def test_update_preserves_old_root_and_config_then_stat_reaches_panel_pick(self):
        self.h.frames[0]['*EL:ROOT*'] = self.root
        cfg = self.calibrated_config()
        self.h.frames[0]['TEST:CFG'] = cfg
        # Existing CAD2020 data uses the default codepage rather than UTF-8.
        self.config_path().write_text(lisp_data(cfg), encoding='gb2312')
        before = self.config_path().read_bytes()
        self.h.run(self.update)
        self.assertEqual(self.h.lookup('*EL:ROOT*'), self.root)
        self.assertEqual(self.h.run('(EL:LoadConfig)'), cfg)
        self.h.run('(c:ELSTAT)')
        self.assertEqual(self.dialogs, [])
        self.assertEqual(len(self.picks), 1)
        self.assertIn('拾取配电箱', self.picks[0])
        self.assertEqual(self.config_path().read_bytes(), before)
        self.assertTrue(all(not encoding for _, _, encoding in self.opens))

    def test_update_cancel_reports_not_ready_and_command_can_retry_once(self):
        self.h.functions.clear()
        self.selections = iter([None, (self.built / 'src/load.lsp').as_posix()])
        self.h.run(self.update)
        self.assertNotIn('目录已确认', ''.join(self.messages))
        self.assertIn('未确认插件目录', ''.join(self.messages))
        self.assertIsNone(self.h.lookup('*EL:ROOT*'))
        self.h.run('(c:ELSETUP)')
        self.assertEqual(len(self.dialogs), 2)
        self.assertEqual(len(self.picks), 1)
        self.assertEqual(self.opens, [])

    def test_packaged_setup_uses_fixed_mm_and_numeric_choices_with_real_data_io(self):
        self.h.frames[0]['*EL:ROOT*'] = self.root
        self.h.run(self.update)
        entities = {
            name: [Pair(0, typ), Pair(5, name), Pair(8, layer), Pair(2, name + '-block')]
            for name, typ, layer in (('panel', 'INSERT', 'P'), ('wire', 'LINE', 'W'),
                                     ('lamp', 'INSERT', 'D'))
        }
        picks = iter(entities)
        choices = iter([None, 1])
        prompts = []

        def pick(prompt):
            self.picks.append(prompt)
            return [next(picks), [0.0, 0.0, 0.0]]

        def choice(prompt):
            prompts.append(prompt)
            return next(choices)

        self.h.builtins.update({
            'ENTSEL': pick,
            'ENTGET': lambda entity: entities[entity],
            'EL:EFFECTIVENAME': lambda entity: entity + '-block',
            'REDRAW': lambda *args: None,
            'GETSTRING': lambda *args: self.fail('Packaged setup must not ask for units'),
            'GETKWORD': lambda prompt: None,
            'GETINT': choice,
            'INITGET': lambda *args: None,
        })
        self.h.run('(c:ELSETUP)')
        saved = self.h.run('(EL:LoadConfig)')
        self.assertEqual(self.get('units', saved), 'mm')
        self.assertTrue(truth(self.get('calibrated', saved)))
        self.assertEqual(len(self.picks), 3)
        self.assertEqual(len(prompts), 2)
        self.assertNotIn('Keep', ''.join(prompts))
        self.assertTrue(all(not encoding for _, _, encoding in self.opens))
        self.assertIsNone(self.h.lookup('*EL:PICKHIGHLIGHTS*'))
        choices = iter([None])
        prompts.clear()
        self.h.run('(c:ELSETUP)')
        self.assertEqual(len(prompts), 1)
        self.assertEqual(len(self.picks), 3)
        self.assertTrue(truth(self.get('calibrated', self.h.run('(EL:LoadConfig)'))))

    def test_package_encoding_layout_and_update_forms(self):
        for path in self.built.rglob('*'):
            if path.suffix in ('.lsp', '.dcl'):
                data = path.read_bytes()
                text = data.decode('gb2312')
                self.assertEqual(text.encode('gb2312'), data)
                self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
                if path.suffix == '.lsp':
                    self.assertTrue(parse(text))
        with zipfile.ZipFile(self.built.with_suffix('.zip')) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertIn(f'{self.builder.NAME}/{self.builder.UPDATE_NAME}', names)
            for folder in ('config', 'output', 'templates'):
                self.assertIn(f'{self.builder.NAME}/{folder}/', names)
        self.assertIn('(open path "r")', self.update)
        self.assertIn('(open tmp "w")', self.update)
        self.assertNotIn('(open path "r" "utf8")', self.update)
        self.assertNotIn('(getvar "LISPSYS")', (self.built / 'src/load.lsp').read_bytes().decode('gb2312'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
