"""Owned assets and preview job boundaries. Date: 2026-10-11. CAD export itself is native-only."""
from pathlib import Path
import tempfile
import unittest

import test_device_library as backend
from autolisp_host import Pair, Symbol, parse, truth


# Date: 2026-10-11. Independent golden bytes from Autodesk's annotated SLD dump:
# https://help.autodesk.com/cloudhelp/2015/ENU/AutoCAD-DXF/files/GUID-11E004A5-B63D-44A7-BE69-939E7EA4F901.htm
# The header table's decimal wording conflicts with its hex example; native type is 0x56.
AUTODESK_VECTOR_SLIDE = bytes.fromhex(
    '41 75 74 6F 43 41 44 20 53 6C 69 64 65 0D 0A 1A 00 56 02 '
    '3C 02 24 01 0B 80 DF 00 02 00 34 12 '
    '07 FF 3C 02 24 01 00 00 00 00 '
    '03 FF 0F 00 32 00 0F 00 13 00 '
    '01 FF 12 FB E7 12 CE DF FE 00 00 FE E7 21 FE 00 00 FC'
)


class DeviceAssetsTests(unittest.TestCase):
    setUp = backend.DeviceLibraryTests.setUp
    call = backend.DeviceLibraryTests.call
    get = backend.DeviceLibraryTests.get
    put = backend.DeviceLibraryTests.put
    entry = backend.DeviceLibraryTests.entry
    fs = backend.DeviceLibraryTests.fs

    def binary(self):
        self.h.builtins['EL:DLBYTES'] = lambda p,n: list(Path(p).read_bytes() if n == -1 else Path(p).read_bytes()[:n])
        self.h.builtins['VL-FILE-SIZE'] = lambda p: Path(p).stat().st_size
        self.h.builtins['EL:DLFILESEQUAL'] = lambda a,b: Path(a).read_bytes() == Path(b).read_bytes()
        self.h.builtins['EL:DLFOLDERCLAIM'] = lambda p: Path(p).mkdir() or True

    def slide(self, width=800, height=600):
        data = bytearray(AUTODESK_VECTOR_SLIDE)
        data[19:23] = (width-1).to_bytes(2, 'little') + (height-1).to_bytes(2, 'little')
        data[23:27] = round(width / height * 10_000_000).to_bytes(4, 'little')
        return bytes(data)

    def test_documented_native_slide_type_and_endian_marker(self):
        with tempfile.TemporaryDirectory() as d:
            self.fs(d); self.binary()
            path = str(Path(d) / 'native.sld')
            Path(path).write_bytes(AUTODESK_VECTOR_SLIDE)
            self.assertEqual(self.call('EL:DLSLDSize', path), [573, 293])
            swapped = bytearray(AUTODESK_VECTOR_SLIDE)
            for offset in (19, 21, 27, 29):
                swapped[offset:offset+2] = reversed(swapped[offset:offset+2])
            Path(path).write_bytes(swapped)
            self.assertEqual(self.call('EL:DLSLDSize', path), [573, 293])
            for offset, value in ((17, 0x38), (18, 1), (29, 0)):
                invalid = bytearray(AUTODESK_VECTOR_SLIDE)
                invalid[offset] = value
                Path(path).write_bytes(invalid)
                self.assertFalse(truth(self.call('EL:DLSLDSize', path)))

    def test_header_rejects_corrupt_assets_and_reads_actual_pixel_size(self):
        with tempfile.TemporaryDirectory() as d:
            self.fs(d); self.binary()
            path = str(Path(d)/'preview.sld')
            for content in (b'', b'bad', self.slide().replace(b'Slide', b'slide'), self.slide()[:25]):
                Path(path).write_bytes(content)
                self.assertFalse(truth(self.call('EL:DLSLDSize', path)))
            Path(path).write_bytes(self.slide())
            self.assertEqual(self.call('EL:DLSLDSize', path), [800,600])
            path = str(Path(d)/'block.dwg')
            Path(path).write_bytes(b'AC1032mock')
            self.assertTrue(truth(self.call('EL:DLDWGValid', path)))
            Path(path).write_bytes(b'notDWG')
            self.assertFalse(truth(self.call('EL:DLDWGValid', path)))

    def test_asset_versions_are_immutable_and_failed_copy_is_never_a_catalog_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fs(d); self.binary()
            snap = self.call('EL:DLSnapshotLoad', root)
            dwg,slide = str(Path(d)/'sample.dwg'), str(Path(d)/'sample.sld')
            Path(dwg).write_bytes(b'AC1032first'); Path(slide).write_bytes(self.slide())
            row = self.entry(ready=False)
            first = self.call('EL:DLAssetInstall', snap, row, dwg, slide)
            self.assertEqual(self.get('asset-revision', first), 1)
            Path(dwg).write_bytes(b'AC1032second')
            second = self.call('EL:DLAssetInstall', snap, first, dwg, slide)
            self.assertEqual(self.get('asset-revision', second), 2)
            self.assertEqual(Path(d,'assets/ELDEV1/1/block.dwg').read_bytes(), b'AC1032first')
            self.h.builtins['VL-FILE-COPY'] = lambda *args: None
            with self.assertRaises(RuntimeError): self.call('EL:DLAssetInstall', snap, second, dwg, slide)
            self.assertFalse(Path(d,'catalog.eld').exists())

    def test_normal_legend_reuse_does_not_export_or_regenerate_or_mutate_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fs(d); self.binary()
            path = Path(d,'assets/ELDEV1/1/legend.sld'); path.parent.mkdir(parents=True); path.write_bytes(self.slide())
            snap = [Pair(Symbol('ROOT'), root)]
            row = self.put('legend-checksum', self.call('EL:DLChecksum', str(path)), self.entry())
            for api in ('COMMAND','COMMAND-S','VLA-REGEN','VLA-WBLOCK','VLA-PUT-VISIBLE','ENTMOD'):
                self.h.builtins[api] = lambda *args: self.fail('cached legend must be read-only')
            self.assertEqual(self.call('EL:DLLegend', row, snap), [str(path).replace('\\','/'), [800,600]])
            path.write_bytes(self.slide()[:-1] + b'X')
            self.assertFalse(truth(self.call('EL:DLLegend', row, snap)))
            path.unlink()
            self.assertFalse(truth(self.call('EL:DLLegend', row, snap)))

    def test_saved_graphic_is_visible_before_draft_power_and_ground_are_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fs(d); self.binary()
            path = Path(d, 'assets/ELDEV1/1/legend.sld')
            path.parent.mkdir(parents=True); path.write_bytes(self.slide())
            row = self.put('watts', None, self.put('ground-confirmed', None, self.entry()))
            row = self.put('status', Symbol('DRAFT'), self.put('active', None, row))
            row = self.put('legend-checksum', self.call('EL:DLChecksum', str(path)), row)
            self.assertFalse(truth(self.call('EL:DLEntryReady', row)))
            self.assertEqual(self.call('EL:DLLegend', row, [Pair(Symbol('ROOT'), root)]),
                             [str(path).replace('\\', '/'), [800, 600]])

    def test_capture_callback_accepts_documented_native_slide_and_retains_draft(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fs(d); self.binary()
            stage = Path(d, '.staging/op-1'); stage.mkdir(parents=True)
            dwg, slide, marker = [str(stage / name).replace('\\', '/')
                                  for name in ('block.dwg', 'legend.sld', 'complete.txt')]
            Path(dwg).write_bytes(b'AC1032mock')
            Path(slide).write_bytes(AUTODESK_VECTOR_SLIDE)
            Path(marker).write_text('DONE\n', encoding='utf-8')
            draft = self.entry(ready=False)
            job = [Pair(Symbol(k), v) for k, v in {'TOKEN': 'op-1', 'DWG': dwg, 'SLIDE': slide,
                'MARKER': marker, 'ENTRY': draft, 'SNAPSHOT': [Pair(Symbol('ROOT'), root)]}.items()]
            self.h.set('*EL:DLCAPTUREJOB*', job)
            self.h.builtins['EL:DLCAPTURECLOSE'] = lambda _: True
            result = self.call('EL:DLCaptureResume', 'op-1')
            self.assertEqual(self.get('captured', result), job)
            self.assertEqual(self.get('device-id', result), self.get('device-id', draft))
            self.assertTrue(Path(slide).exists())
            self.assertIsNone(self.h.lookup('*EL:DLCAPTUREJOB*'))

    def test_export_cleans_only_its_selection_set_even_on_native_failure(self):
        deleted = []
        self.h.builtins['VLAX-GET-ACAD-OBJECT'] = lambda: 'app'
        self.h.builtins['VLA-GET-ACTIVEDOCUMENT'] = lambda _: 'source'
        def export(*args):
            self.h.set('*EL:DLEXPORTSET*','owned-set')
            raise RuntimeError('native failure')
        self.h.builtins['EL:DLEXPORTWORK'] = export
        self.h.builtins['VLA-DELETE'] = lambda obj: deleted.append(obj)
        self.assertFalse(truth(self.call('EL:DLExport','entity','file')))
        self.assertEqual(deleted, ['owned-set'])

    def test_queue_script_is_valid_lisp_with_escaped_paths_and_cross_document_callback(self):
        job = [Pair(Symbol(k),v) for k,v in {'SLIDE':'C:/设备库/"x"/legend.sld','MARKER':'C:/库/complete.txt',
            'SOURCE-NAME':'图纸 A.dwg','TOKEN':'op-123'}.items()]
        script = self.call('EL:DLCaptureScript',job)
        self.assertTrue(parse(script))
        self.assertIn('EL:DLCaptureResume',script)
        self.assertIn('vla-SendCommand',script)
        self.assertIn('MSLIDE',script)
        self.assertIn('vla-get-FullName',script)
        self.assertNotIn('EL:ThumbIsolate',script)

    def test_stale_callback_never_closes_any_document_or_publishes(self):
        self.h.set('*EL:DLCAPTUREJOB*',[Pair(Symbol('TOKEN'),'new-job')])
        self.h.builtins['EL:DLCAPTURECLOSE'] = lambda *_: self.fail('wrong token must not close')
        self.assertFalse(truth(self.call('EL:DLCaptureResume','old-job')))
        self.assertIsNotNone(self.h.lookup('*EL:DLCAPTUREJOB*'))

    def test_capture_restores_command_settings_after_success_and_slide_failure(self):
        job = [Pair(Symbol('SLIDE'), 'C:/owned/legend.sld'), Pair(Symbol('MARKER'), 'C:/owned/complete.txt')]
        forms = parse(self.call('EL:DLCaptureScript', job))[0][1:]
        prefix = []
        for form in forms:
            if form[:2] == [Symbol('SETQ'), Symbol('EL_DL_FILE')]: break
            prefix.append(form)
        self.h.builtins.update({
            'VL-LOAD-COM': lambda: None, 'VLAX-GET-ACAD-OBJECT': lambda: 'app',
            'VLA-GET-ACTIVEDOCUMENT': lambda _: 'temporary',
            'VLA-ZOOMEXTENTS': lambda _: None, 'VLA-REGEN': lambda *_: None,
        })
        for failed in (False, True):
            with self.subTest(slide_failed=failed):
                values = {'FILEDIA': 1, 'CMDECHO': 1, 'TILEMODE': 0, 'UCSFOLLOW': 1}
                commands = []
                self.h.builtins['GETVAR'] = lambda key: values[key]
                self.h.builtins['SETVAR'] = lambda key, value: values.__setitem__(key, value) or value
                def command(*args):
                    commands.append(args)
                    if args[0] == '_.MSLIDE' and failed: raise RuntimeError('native slide failed')
                self.h.builtins['COMMAND-S'] = command
                self.h.body(prefix)
                self.assertEqual((values['FILEDIA'], values['CMDECHO']), (1, 1))
                self.assertIn(('_.ZOOM', '0.8x'), commands)
                self.assertEqual(truth(self.h.call('VL-CATCH-ALL-ERROR-P', [self.h.lookup('EL_DL_OUTCOME')])), failed)

    def test_cleanup_refuses_to_close_document_not_owned_by_job(self):
        self.h.builtins['VLA-GET-FULLNAME'] = lambda _: 'C:/user.dwg'
        self.h.builtins['VL-STRING-TRANSLATE'] = lambda old,new,v:v.replace(old,new)
        self.h.builtins['VLA-CLOSE'] = lambda *_: self.fail('must not close user drawing')
        job = [Pair(Symbol('TEMPORARY'),'doc'),Pair(Symbol('DWG'),'C:/owned.dwg')]
        self.assertFalse(truth(self.call('EL:DLCaptureClose',job)))

    def test_close_failure_preserves_job_and_does_not_publish_or_delete_staging(self):
        job=[Pair(Symbol('TOKEN'),'op-1'),Pair(Symbol('FAILED'),True)]
        self.h.set('*EL:DLCAPTUREJOB*',job)
        self.h.builtins['EL:DLCAPTURECLOSE']=lambda *_:None
        self.h.builtins['EL:DLCAPTURECLEANUP']=lambda *_:self.fail('close failed; files must remain')
        self.h.builtins['EL:DLDWGVALID']=lambda *_:self.fail('must not publish')
        self.assertFalse(truth(self.call('EL:DLCaptureResume','op-1')))
        self.assertEqual(self.h.lookup('*EL:DLCAPTUREJOB*'),job)

    def test_stage_cleanup_only_deletes_owned_known_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.fs(d)
            stage=Path(d,'.staging/op-1');stage.mkdir(parents=True)
            for filename in ('block.dwg','legend.sld','complete.txt','keep.txt'): (stage/filename).write_text('sample')
            job=[Pair(Symbol('TOKEN'),'op-1'),Pair(Symbol('SNAPSHOT'),[Pair(Symbol('ROOT'),root)]),
                 Pair(Symbol('DWG'),str(stage/'block.dwg').replace('\\','/'))]
            self.call('EL:DLCaptureCleanup',job)
            self.assertEqual([p.name for p in stage.iterdir()],['keep.txt'])
            (stage/'block.dwg').write_text('sample')
            job=self.put('token','../other',job)
            self.call('EL:DLCaptureCleanup',job)
            self.assertTrue((stage/'block.dwg').exists())


if __name__ == '__main__': unittest.main()
