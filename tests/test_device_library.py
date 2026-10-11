"""Independent catalog contracts. Date: 2026-10-11. Not native CAD acceptance."""
from pathlib import Path
import tempfile
import unittest

from autolisp_host import Host, Symbol, Pair, truth
from test_diagram_store import dump as printer

ROOT = Path(__file__).resolve().parents[1]


class DeviceLibraryTests(unittest.TestCase):
    def setUp(self):
        self.h = Host()
        for path in (ROOT / 'src').glob('*.lsp'):
            self.h.load_definitions(path)
        self.h.builtins['VL-PRIN1-TO-STRING'] = printer
        self.h.builtins['VL-STRING-RIGHT-TRIM'] = lambda chars, value: value.rstrip(chars)
        self.h.builtins['EL:LOGEVENT'] = lambda *args: None
        self.h.builtins['EXIT'] = lambda: (_ for _ in ()).throw(RuntimeError('validation failed'))
        self.cat = self.call('EL:DLCatalogInitial', 'LIB-TEST')

    def call(self, name, *args):
        return self.h.call(name.upper(), list(args))

    def get(self, key, value):
        return self.call('EL:Get', Symbol(key.upper()), value)

    def put(self, key, value, row):
        return self.call('EL:Put', Symbol(key.upper()), value, row)

    def entry(self, name='灯具A', watts=5, ground=None, ready=True):
        row = self.call('EL:DLEntryNew', self.cat, name)
        values = {'display': '应急灯 "A"\\样例', 'watts': watts,
                  'is-ground': ground, 'ground-confirmed': True, 'zero-confirmed': watts == 0 or None}
        if ready:
            id_ = self.get('device-id', row)
            values.update({'active': True, 'status': Symbol('READY'), 'asset-revision': 1,
                           'block-file': f'assets/{id_}/1/block.dwg', 'legend-file': f'assets/{id_}/1/legend.sld',
                           'legend-size': [800, 600], 'legend-checksum': 'sld-123-31'})
        for key, value in values.items():
            row = self.put(key, value, row)
        return row

    def add(self, row=None):
        self.cat = self.call('EL:DLUpsert', self.cat, row or self.entry())
        self.assertTrue(truth(self.cat))
        return self.get('devices', self.cat)[-1]

    def test_create_update_delete_restore_preserve_identity_and_history_values(self):
        row = self.add()
        old = self.cat
        changed = self.put('watts', 8, row)
        self.cat = self.call('EL:DLUpsert', self.cat, changed)
        self.assertEqual(self.get('watts', self.get('devices', old)[0]), 5)
        self.assertEqual(self.get('watts', self.get('devices', self.cat)[0]), 8)
        id_ = self.get('device-id', row)
        self.cat = self.call('EL:DLDelete', self.cat, id_)
        self.assertFalse(truth(self.call('EL:DLIndex', self.cat)))
        self.cat = self.call('EL:DLRestore', self.cat, id_)
        self.assertEqual(self.get('device-id', self.get('devices', self.cat)[0]), id_)
        self.assertEqual(self.get('revision', self.cat), 4)

    def test_names_are_exact_case_insensitive_and_explicit_aliases_only(self):
        self.add(self.put('aliases', ['Exit Sign'], self.entry('Lamp A')))
        snap = [Pair(Symbol('INDEX'), self.call('EL:DLIndex', self.cat))]
        self.assertTrue(truth(self.call('EL:DLLookup', 'lAMP a', snap)))
        self.assertTrue(truth(self.call('EL:DLLookup', 'EXIT SIGN', snap)))
        for value in ('Lamp', 'Lamp A2', '*U42', 'Exit', ' Lamp A'):
            self.assertFalse(truth(self.call('EL:DLLookup', value, snap)))

    def test_conflicting_name_or_alias_rejects_without_changing_old_catalog(self):
        self.add(self.put('aliases', ['旧块名'], self.entry('Lamp')))
        old = self.cat
        for name in ('lamp', '旧块名'):
            self.assertFalse(truth(self.call('EL:DLUpsert', self.cat, self.entry(name))))
            self.assertEqual(self.cat, old)

    def test_stale_entry_revision_cannot_overwrite_newer_edit(self):
        row = self.add()
        self.cat = self.call('EL:DLUpsert', self.cat, self.put('watts', 6, row))
        self.assertFalse(truth(self.call('EL:DLUpsert', self.cat, self.put('watts', 7, row))))

    def test_delete_restore_checks_name_conflicts(self):
        row = self.add()
        id_ = self.get('device-id', row)
        self.cat = self.call('EL:DLDelete', self.cat, id_)
        self.add(self.entry())
        self.assertFalse(truth(self.call('EL:DLRestore', self.cat, id_)))

    def test_draft_is_searchable_but_cannot_match_or_imply_non_ground(self):
        row = self.call('EL:DLEntryNew', self.cat, '待补图块')
        self.add(row)
        self.assertFalse(truth(self.call('EL:DLIndex', self.cat)))
        self.assertEqual(len(self.call('EL:DLSearch', self.cat, '待补', None)), 1)
        self.assertFalse(truth(self.get('ground-confirmed', self.get('devices', self.cat)[0])))

    def test_watts_zero_and_ground_confirmation_are_explicit(self):
        for value in (-1, 1.5, 2147483648, '5'):
            self.assertFalse(truth(self.call('EL:DLUpsert', self.cat, self.entry(watts=value))))
        self.assertFalse(truth(self.call('EL:DLUpsert', self.cat, self.put('zero-confirmed', None, self.entry(watts=0)))))
        self.assertFalse(truth(self.call('EL:DLUpsert', self.cat, self.put('ground-confirmed', None, self.entry()))))
        self.add(self.entry(watts=0, ground=None))

    def test_asset_paths_are_tied_to_id_and_revision(self):
        for field, value in [('device-id', '../outside'), ('block-file', '../../outside.dwg'),
                             ('legend-file', 'C:/outside.sld'), ('legend-size', [0, 600])]:
            self.assertFalse(truth(self.call('EL:DLUpsert', self.cat, self.put(field, value, self.entry()))))

    def test_strict_utf8_rejects_overlong_surrogates_truncation_nul_and_out_of_range(self):
        for text in ('设备库', 'A "B"\\C', '\U0001f31f'):
            self.assertTrue(truth(self.call('EL:DLUTF8Valid', list(text.encode('utf-8')))))
        for data in ([0], [0xc0, 0x80], [0xed, 0xa0, 0x80], [0xf4, 0x90, 0x80, 0x80], [0xe4, 0xb8], [0xff]):
            self.assertFalse(truth(self.call('EL:DLUTF8Valid', data)))

    def test_catalog_roundtrip_preserves_chinese_quotes_slashes_and_false_ground(self):
        self.add()
        raw = printer(self.cat)
        self.assertEqual(self.call('EL:DLParse', raw), self.cat)
        self.assertFalse(truth(self.call('EL:DLParse', raw + ' (unexpected)')))
        self.assertFalse(truth(self.call('EL:DLParse', '(bad)')))

    def test_unknown_schema_and_duplicate_ids_are_rejected(self):
        self.add()
        self.assertFalse(truth(self.call('EL:DLCatalogValid', self.put('schema', Symbol('FUTURE'), self.cat))))
        self.assertFalse(truth(self.call('EL:DLCatalogValid', self.put('devices', self.get('devices', self.cat)*2, self.cat))))

    def test_long_strings_use_bounded_reader_fragments(self):
        self.add(self.put('display', '设备名\\"' * 400, self.entry()))
        original = self.h.builtins['READ']
        sizes = []
        def read(text):
            sizes.append(len(text.encode('gb2312')))
            if sizes[-1] > 256: raise RuntimeError('输入的字符串太长')
            return original(text)
        self.h.builtins['READ'] = read
        self.assertEqual(self.call('EL:DLParse', printer(self.cat)), self.cat)
        self.assertGreater(len(sizes), 10)

    def fs(self, directory):
        root = str(directory).replace('\\', '/') + '/'
        self.h.builtins.update({
            'FINDFILE': lambda p: p if Path(p).is_file() else None,
            'VL-FILE-DIRECTORY-P': lambda p: True if Path(p).is_dir() else None,
            'EL:DLMKDIR': lambda p: Path(p).mkdir(parents=True, exist_ok=True) or True,
            'EL:DLREADTEXT': lambda p: Path(p).read_text(encoding='utf-8-sig'),
            'EL:DLWRITETEXT': lambda p, s: Path(p).write_text(s, encoding='utf-8') or True,
            'VL-FILE-RENAME': lambda a,b: Path(a).rename(b) or True,
            'VL-FILE-COPY': lambda a,b: Path(b).write_bytes(Path(a).read_bytes()) or True,
            'VL-FILE-DELETE': lambda p: Path(p).unlink(missing_ok=True) or True,
            'VL-FILENAME-MKTEMP': lambda prefix, folder, ext: str(Path(folder)/(prefix+str(len(list(Path(folder).glob('*'))))+ext)),
            'VL-FILENAME-DIRECTORY': lambda p:str(Path(p).parent),
            'EL:DLOPERATIONID': lambda: 'op-test',
            'OPEN': lambda p,m: open(p, m, encoding='ascii'),
            'READ-LINE': lambda f: f.readline().rstrip('\r\n') or None,
            'CLOSE': lambda f: f.close(),
            'VL-FILE-SIZE': lambda p: Path(p).stat().st_size,
            'VL-DIRECTORY-FILES': lambda p,pattern,mode: [f.name for f in Path(p).glob(pattern) if f.is_file()],
            'EL:DLLockAcquire'.upper(): lambda p,o: Path(p).write_text(o) or True,
        })
        return root

    def test_publish_utf8_exact_readback_and_immutable_previous_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            snap = self.call('EL:DLSnapshotLoad', root)
            candidate = self.call('EL:DLUpsert', self.get('catalog', snap), self.entry())
            self.assertTrue(truth(self.call('EL:DLCommit', snap, candidate)))
            snap = self.call('EL:DLSnapshotLoad', root)
            old = self.get('raw', snap)
            candidate = self.call('EL:DLDelete', self.get('catalog', snap), 'ELDEV1')
            self.assertTrue(truth(self.call('EL:DLCommit', snap, candidate)))
            self.assertEqual((Path(folder)/'history/1.eld').read_text(encoding='utf-8'), old)
            self.assertFalse((Path(folder)/'.write-lock').exists())

    def test_concurrent_catalog_change_rejects_even_when_revision_not_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            self.add()
            Path(folder, 'catalog.eld').write_text(printer(self.cat), encoding='utf-8')
            snap = self.call('EL:DLSnapshotLoad', root)
            Path(folder, 'catalog.eld').write_text(printer(self.cat)+'\n', encoding='utf-8')
            candidate = self.call('EL:DLDelete', self.cat, 'ELDEV1')
            self.assertFalse(truth(self.call('EL:DLCommit', snap, candidate)))
            self.assertTrue(Path(folder, 'catalog.eld').read_text(encoding='utf-8').endswith('\n'))
            self.assertFalse(Path(folder, '.write-lock').exists())

    def test_failed_publish_restores_previous_catalog_and_releases_own_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            self.add()
            original = printer(self.cat)
            Path(folder, 'catalog.eld').write_text(original, encoding='utf-8')
            snap = self.call('EL:DLSnapshotLoad', root)
            def rename(a,b):
                if '.staging' in a: return None
                Path(a).rename(b)
                return True
            self.h.builtins['VL-FILE-RENAME'] = rename
            candidate = self.call('EL:DLDelete', self.cat, 'ELDEV1')
            self.assertFalse(truth(self.call('EL:DLCommit', snap, candidate)))
            self.assertEqual(Path(folder, 'catalog.eld').read_text(encoding='utf-8'), original)
            self.assertFalse(Path(folder, '.write-lock').exists())

    def test_reader_does_not_treat_publish_gap_as_empty_library(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            Path(folder, '.write-lock').write_text('other-owner')
            self.assertFalse(truth(self.call('EL:DLSnapshotLoad', root)))

    def test_release_reads_ascii_crlf_owner_without_catalog_decoder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            path = root + '.write-lock'
            Path(path).write_bytes(b'op-test\r\n')
            self.h.builtins['EL:DLREADTEXT'] = lambda _: self.fail('catalog decoder used for lock')
            self.assertTrue(truth(self.call('EL:DLLockRelease', path, 'op-test')))
            self.assertFalse(Path(path).exists())

    def test_release_never_removes_other_owner_or_unreadable_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            path = root + '.write-lock'
            Path(path).write_bytes(b'other-owner\r\n')
            self.assertFalse(truth(self.call('EL:DLLockRelease', path, 'op-test')))
            self.h.builtins['OPEN'] = lambda *args: None
            self.assertFalse(truth(self.call('EL:DLLockRelease', path, 'op-test')))
            self.assertEqual(Path(path).read_bytes(), b'other-owner\r\n')

    def test_lock_write_failure_closes_stream_before_cleanup(self):
        events = []
        def invoke(obj, method, *args):
            events.append(str(method))
            if str(method) == 'CREATETEXTFILE': return 'stream'
            if str(method) == 'WRITELINE': raise RuntimeError('write failed')
        self.h.builtins.update({'VLAX-CREATE-OBJECT': lambda _: 'fso',
            'VLAX-INVOKE-METHOD': invoke,
            'VLAX-RELEASE-OBJECT': lambda obj: events.append('release-' + obj),
            'VL-FILE-DELETE': lambda _: events.append('delete') or True})
        self.assertFalse(truth(self.call('EL:DLLockAcquire', 'owned.lock', 'op-test')))
        self.assertEqual(events, ['CREATETEXTFILE', 'WRITELINE', 'CLOSE', 'release-stream', 'release-fso', 'delete'])

    def test_failed_lock_claim_never_deletes_existing_marker(self):
        def denied(*args): raise RuntimeError('already exists')
        self.h.builtins.update({'VLAX-CREATE-OBJECT': lambda _: 'fso',
            'VLAX-INVOKE-METHOD': denied, 'VLAX-RELEASE-OBJECT': lambda _: None,
            'VL-FILE-DELETE': lambda _: self.fail('deleted someone else lock')})
        self.assertFalse(truth(self.call('EL:DLLockAcquire', 'other.lock', 'op-test')))

    def test_explicit_lock_recovery_archives_marker_and_preserves_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            self.add()
            original = printer(self.cat)
            Path(folder, 'catalog.eld').write_text(original, encoding='utf-8')
            Path(folder, '.write-lock').write_bytes(b'op-old\r\n')
            self.assertTrue(truth(self.call('EL:DLLockRecover', root)))
            self.assertEqual(Path(folder, 'catalog.eld').read_text(encoding='utf-8'), original)
            self.assertEqual(Path(folder, 'lock-recovered-op-test.txt').read_bytes(), b'op-old\r\n')
            self.assertTrue(truth(self.call('EL:DLSnapshotLoad', root)))

    def test_lock_recovery_refuses_incomplete_publish_or_corrupt_catalog(self):
        for relative, content in [('rollback-old.eld', 'old'), ('.staging/catalog-old.eld', 'new'),
                                  ('history/1.eld', 'old'), ('catalog.eld', 'broken')]:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as folder:
                root = self.fs(folder)
                evidence = Path(folder, relative)
                evidence.parent.mkdir(parents=True, exist_ok=True)
                evidence.write_text(content)
                Path(folder, '.write-lock').write_text('op-old')
                self.assertFalse(truth(self.call('EL:DLLockRecover', root)))
                self.assertTrue(Path(folder, '.write-lock').exists())
                self.assertEqual(evidence.read_text(), content)

    def test_empty_first_write_lock_can_recover_without_creating_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            Path(folder, '.write-lock').write_bytes(b'')
            self.assertTrue(truth(self.call('EL:DLLockRecover', root)))
            self.assertFalse(Path(folder, 'catalog.eld').exists())
            self.assertEqual(self.get('revision',self.get('catalog',self.call('EL:DLSnapshotLoad', root))), 0)

    def test_lock_recovery_retains_busy_file_or_unknown_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fs(folder)
            path = Path(folder, '.write-lock')
            path.write_text('unrelated-file')
            self.assertFalse(truth(self.call('EL:DLLockRecover', root)))
            path.write_text('op-old')
            self.h.builtins['VL-FILE-RENAME'] = lambda *args: None
            self.assertFalse(truth(self.call('EL:DLLockRecover', root)))
            self.assertEqual(path.read_text(), 'op-old')


if __name__ == '__main__':
    unittest.main()
