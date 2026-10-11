"""Owned assets and preview job boundaries. Date: 2026-10-11. CAD export itself is native-only."""
from pathlib import Path
import tempfile
import unittest

import test_device_library as backend
from autolisp_host import Pair, Symbol, parse, truth


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
        return b'AutoCAD Slide\r\n\x1a\x00' + bytes([56,2]) + (width-1).to_bytes(2,'little') + (height-1).to_bytes(2,'little') + bytes(8)

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
