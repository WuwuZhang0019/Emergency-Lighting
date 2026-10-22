"""Build the AutoCAD 2020 trial package. Date: 2026-10-22."""
from pathlib import Path
import base64
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# Date: 2026-10-22. Local read-only native prototype; no merge or publication.
VERSION = '0.1.75'
PACKAGE_NO = 174
FULL_TEST_COMMAND = 'ELFULL75'
COLD_TEST_COMMAND = 'ELCOLD75'
NAME = f'应急照明-v{VERSION}'
UPDATE_NAME = f'UPDATE-{PACKAGE_NO:03d}.lsp'
OUTPUT_ROOT = ROOT / 'output'
DEST = OUTPUT_ROOT / NAME
MODULES = ('common', 'config', 'geometry', 'topology', 'statistics', 'device-library', 'device-assets', 'device-defaults', 'device-ui', 'device-recognition', 'device-inputs', 'device-migration', 'generation', 'main', 'simple', 'circuit-number', 'fixed', 'panel', 'store-compact', 'diagram-store', 'store-split', 'diagram-update', 'diagram-commands', 'insert-circuit', 'cold-probe', 'startup')
LOAD_COMPLETION = (
    '(EL:MonitorLoadEnd (if *EL:MonitorLoadReady* \'load-finished \'load-failed))\n'
    '(EL:StartupCommandHint *EL:MonitorLoadReady*)\n(princ)\n'
)


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def lisp_string(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('\r', '\\r').replace('\n', '\\n') + '"'


def embedded_writer(name, assets):
    """Date: 2026-10-14. Batch immutable bytes, including GB2312 LISP/DCL."""
    writes = []
    for path in assets:
        if not path.is_file():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        # Keep every literal below the legacy READ fragment limit.
        chunks = '\n'.join(lisp_string(encoded[i:i + 192]) for i in range(0, len(encoded), 192))
        relative = lisp_string(path.relative_to(DEST).as_posix())
        writes.append(f'(if (and ok (not (EL:StartupResource \'EL:StartupWriteBase64 (strcat root {relative})\n\'({chunks})))) (setq ok nil))')
    return (f'(defun {name} (root / ok)\n  (setq ok T)\n' + '\n'.join(writes) + '\n  ok)\n')


def embedded_resources():
    """Date: 2026-10-14. Separate lookup, code/UI and default-asset timings."""
    text = embedded_writer('EL:StartupEmbeddedText',
        sorted((DEST / 'src').glob('*.lsp')) + sorted((DEST / 'ui').glob('*')))
    assets = embedded_writer('EL:StartupEmbeddedAssets',
        sorted((DEST / 'assets/default-device-library').rglob('*'))
        + sorted((DEST / 'templates').glob('*.dwg'))
        + sorted((DEST / 'native').glob('*.dll')))
    return (text + assets + '(defun EL:StartupEmbeddedRoot (/ base root folder marker ok)\n'
            '  (if (setq base (EL:NormalizeRoot (getenv "LOCALAPPDATA")))\n'
            '    (progn\n'
            '      (setq base (strcat base "Emergency-Lighting/"))\n'
            '      (vl-mkdir base)\n'
            f'      (setq root (strcat base "runtime-{PACKAGE_NO:03d}/")\n'
            f'        marker (strcat root "package-{PACKAGE_NO:03d}.marker"))\n'
            '      (vl-mkdir root)\n'
            '      (setq ok (or (not (findfile marker)) (vl-file-delete marker)))\n'
            '      (if (not ok) (setq *EL:StartupError* (strcat marker " : 无法清除旧完成标记")))\n'
            '      (foreach folder \'("src" "ui" "config" "output" "templates" "native")\n'
            '        (vl-mkdir (strcat root folder)))\n'
            '      (setq ok (and ok\n'
            '        (EL:PerfCall "LOAD_RUNTIME_TEXT" \'EL:StartupEmbeddedText (list root))\n'
            '        (EL:PerfCall "LOAD_RUNTIME_ASSETS" \'EL:StartupEmbeddedAssets (list root))))\n' +
            f'\n      (if (and ok (EL:RootValid root)\n'
            f'        (EL:StartupWriteLines marker \'("Emergency-Lighting {PACKAGE_NO}"))) root))))\n')


def diagnostic_script_definition():
    """Date: 2026-10-15. Keep diagnostics independent of writing a .ps1 at startup."""
    script = (ROOT / 'src/diagnostic-bundle.ps1').read_text(encoding='utf-8')
    chunks = '\n'.join(lisp_string(script[i:i + 192]) for i in range(0, len(script), 192))
    return '(defun EL:DiagnosticScriptText () (EL:MonitorJoin \'(\n' + chunks + '\n)))\n'


def full_test_entry(startup):
    """Date: 2026-10-20. Register only; command owns the complete fallback payload."""
    template = (ROOT / 'tools/templates/full-test.lsp').read_text(encoding='utf-8')
    for key, value in {
        '@COMMAND@': FULL_TEST_COMMAND, '@VERSION@': VERSION,
        '@MARKER@': f'package-{PACKAGE_NO:03d}.marker', '@STARTUP@': startup,
    }.items():
        template = template.replace(key, value)
    return template.encode('gb2312', errors='strict')


def cold_test_entry(startup):
    """Date: 2026-10-22. Registration-only independent native probe entry."""
    template = (ROOT / 'tools/templates/cold-test.lsp').read_text(encoding='utf-8')
    for key, value in {
        '@COMMAND@': COLD_TEST_COMMAND, '@VERSION@': VERSION,
        '@MARKER@': f'package-{PACKAGE_NO:03d}.marker', '@STARTUP@': startup,
    }.items():
        template = template.replace(key, value)
    return template.encode('gb2312', errors='strict')


def cad2020_bytes(source):
    """Date: 2026-10-16. Shared strict conversion for full and lite deliveries."""
    text = source.read_text(encoding='utf-8')
    if source.name == 'load.lsp':
        text = replace_once(text, '(if (and *EL:Root* (>= (getvar "LISPSYS") 1))', '(if *EL:Root*')
        text = replace_once(text, '需要 AutoCAD 2021+ Windows、LISPSYS=1/2（更改后重启）及完整插件目录。', '请选择本包的 src/load.lsp，并保留完整插件目录。')
        text = replace_once(text, '已加载：', f'已加载（CAD2020 v{VERSION}）：')
    if source.name == 'config.lsp':
        text = replace_once(text, '(open path "r" "utf8")', '(open path "r")')
        text = replace_once(text, '(open tmp "w" "utf8")', '(open tmp "w")')
    if source.name == 'common.lsp':
        text = replace_once(text, '(open *EL:LogPath* "a" "utf8")', '(open *EL:LogPath* "a")')
        text = replace_once(text, '(open path "a" "utf8")', '(open path "a")')
        text = replace_once(text, 'AutoCAD 2021+, LISPSYS=1/2.', 'AutoCAD 2020 trial, GB2312 source and system-codepage data.')
    if source.name == 'diagram-commands.lsp':
        text = replace_once(text, '(open tmp "w" "utf8")', '(open tmp "w")')
        text = replace_once(text, '(defun EL:DiagnosticNativeCharset () "utf-8")',
                            '(defun EL:DiagnosticNativeCharset () "gb2312")')
        text += '\n' + diagnostic_script_definition()
    data = text.encode('gb2312', errors='strict')
    assert data.decode('gb2312') == text
    return data


def build():
    # Build from current source before touching any existing delivery directory.
    from build_cold_recognition import build as build_native, DLL_NAME
    native_evidence = build_native()
    assert native_evidence['version'] == VERSION
    output_root = OUTPUT_ROOT.resolve()
    assert DEST.resolve().parent == output_root and DEST.name == NAME
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    for folder in ('src', 'ui', 'config', 'output', 'templates', 'native', 'docs', 'tests/fixtures'):
        (DEST / folder).mkdir(parents=True, exist_ok=True)
    shutil.copy2(native_evidence['artifact']['path'], DEST / 'native' / DLL_NAME)
    (DEST / 'native/build.json').write_text(
        json.dumps(native_evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(ROOT / 'native/ColdRecognition/README.md', DEST / 'native/只读原型说明.md')
    # Formal seed assets are versioned source, separate from the mutable user library.
    defaults = ROOT / 'assets/default-device-library'
    assert (defaults / 'catalog.eld').is_file()
    assert len(list((defaults / 'assets').rglob('block.dwg'))) == 49
    assert len(list((defaults / 'assets').rglob('block.dxf'))) == 4
    assert len(list((defaults / 'assets').rglob('legend.sld'))) == 53
    shutil.copytree(defaults, DEST / 'assets/default-device-library', dirs_exist_ok=True)
    # Date: 2026-10-15. Preserve the author's dynamic blocks as original DWG bytes.
    block_library = ROOT / 'templates/系统图块库.dwg'
    assert block_library.is_file(), '缺少 templates/系统图块库.dwg，不能生成完整交付包'
    with block_library.open('rb') as stream:
        assert stream.read(6) in (b'AC1015', b'AC1018', b'AC1021', b'AC1024', b'AC1027', b'AC1032'), '图块库不是 AutoCAD 2020 支持的 DWG 版本'
    shutil.copy2(block_library, DEST / 'templates' / block_library.name)
    shutil.copy2(ROOT / 'src/diagnostic-bundle.ps1', DEST / 'src/diagnostic-bundle.ps1')
    for folder, pattern in (('src', '*.lsp'), ('ui', '*.dcl')):
        for source in (ROOT / folder).glob(pattern):
            data = cad2020_bytes(source)
            (DEST / folder / source.name).write_bytes(data)
    standalone = (DEST / 'src/insert-circuit.lsp').read_bytes() + f'\n(princ "\\nCCKK / CCKK1 / CCKK2 已加载（v{VERSION}）：CCKK 回路，CCKK1 配电箱，CCKK2 整组箱体与回路。")\n(princ)\n'.encode('gb2312', errors='strict')
    (DEST / 'CCKK.lsp').write_bytes(standalone)
    shutil.copy2(ROOT / 'ui/box-ui-011.marker', DEST / 'ui/box-ui-011.marker')
    shutil.copy2(ROOT / 'ui/diagram-ui-044.marker', DEST / 'ui/diagram-ui-044.marker')
    marker = f"package-{PACKAGE_NO:03d}.marker"
    (DEST / marker).write_text(f"Emergency-Lighting {PACKAGE_NO}\n", encoding="ascii")
    # Keep an existing valid data root; initialize it for a standalone update.
    # All modules are included; readiness requires a complete package directory.
    modules = MODULES
    module_texts = []
    for module in modules:
        text = (DEST / 'src' / f'{module}.lsp').read_bytes().decode('gb2312')
        if module == 'common':
            module_texts.append(text + '\n(EL:MonitorLoadBegin *EL:BootstrapTick*)\n')
        else:
            module_texts.append(f'(setq *EL:MonitorLabel* "{module}.lsp" *EL:LoadToken* (EL:PerfBegin "LOAD_MODULE"))\n'
                                + text + '\n(EL:PerfEnd *EL:LoadToken* \'returned)\n(setq *EL:MonitorLabel* nil)\n')
    update = (';; Date: 2026-10-14. Monitor APPLOAD from its first executable form.\n'
              '(setq *EL:BootstrapTick* (getvar "MILLISECS"))\n(vl-load-com)\n' + '\n'.join(module_texts) +
              '\n(EL:ClearPickHighlights)\n(setq *EL:Result* nil *EL:DeviceResult* nil)\n'
              f'(setq *EL:PackageMarker* "{marker}")\n'
              '(if (setq *EL:MonitorLoadReady* (EL:PerfCall "LOAD_ROOT" \'EL:EnsureRoot nil))\n'
              '  (progn (EL:PerfCall "LOAD_LIBRARY" \'EL:DLDefaultStartup nil)\n'
              f'    (princ "\\n已加载（CAD2020 v{VERSION}）：目录已确认。"))\n'
              f'  (princ "\\nCAD2020 v{VERSION} 模块已载入，但未确认插件目录。运行 ELSETUP 或 ELSTAT 后选择完整包内的 src/load.lsp。"))\n'
              + LOAD_COMPLETION)
    (DEST / UPDATE_NAME).write_bytes(update.encode('gb2312'))
    # Date: 2026-10-10. Resolve APPLOAD folder, then validate version and assets.
    startup = replace_once(update, '(setq *EL:MonitorLoadReady* (EL:PerfCall "LOAD_ROOT" \'EL:EnsureRoot nil))',
                           f'(setq *EL:MonitorLoadReady* (EL:PerfCall "LOAD_ROOT" \'EL:StartupRoot (list "{marker}")))')
    startup = startup.replace('(if (setq *EL:MonitorLoadReady*', embedded_resources() + '\n(if (setq *EL:MonitorLoadReady*', 1)
    startup = startup.replace('运行 ELSETUP 或 ELSTAT 后选择完整包内的 src/load.lsp。',
                              '请根据上方具体错误修复后重新加载启动文件。')
    (DEST / 'START-CAD2020.lsp').write_bytes(startup.encode('gb2312', errors='strict'))
    (DEST / 'src/load.lsp').write_bytes(startup.encode('gb2312', errors='strict'))
    (DEST / f'{FULL_TEST_COMMAND}.lsp').write_bytes(full_test_entry(startup))
    (DEST / f'{COLD_TEST_COMMAND}.lsp').write_bytes(cold_test_entry(startup))
    guide = (ROOT / 'docs/03_加载使用与验收说明.md').read_text(encoding='utf-8')
    guide = guide.replace('状态：源码及自动检查已交付，CAD 实测待执行。', f'状态：AutoCAD 2020 兼容试用包 v{VERSION}，真实 CAD 验收待完成。')
    guide = guide.replace('目标为 Windows AutoCAD 2021+，`LISPSYS=1` 或 `2`（修改后需重启）', '本包供简体中文 Windows AutoCAD 2020 试用，LISP/DCL 已转换为 GB2312，无需设置 LISPSYS')
    guide = guide.replace('配置和结果使用 UTF-8 数据关联表', '本包配置和结果使用系统默认编码的数据关联表（简体中文 Windows 通常为 GBK），不要混用旧包配置')
    (DEST / 'docs/03_加载使用与验收说明.md').write_text(guide, encoding='utf-8')
    release_notes = (sorted((ROOT / 'docs/更新记录').glob(f'v{VERSION}-*.md'))
                     or sorted((ROOT / 'docs/更新记录').glob(f'{PACKAGE_NO:03d}-*.md')))
    for source in release_notes:
        shutil.copy2(source, DEST / '本次更新.md')
    shutil.copy2(ROOT / 'docs/04_整箱自动分回路统计与设备功率赋值方案.md',
                 DEST / 'docs/04_整箱自动分回路统计与设备功率赋值方案.md')
    (DEST / 'tests/evidence').mkdir(exist_ok=True)
    for filename in ('2026-10-08-box-statistics.md', '2026-10-08-trace-diagnostics.md', '2026-10-08-contour-diagnostics.md', '2026-10-08-polyline-ocs-fix.md', '2026-10-08-curve-ocs-fix.md', '2026-10-08-region-performance.md', '2026-10-08-contact-performance.md', '2026-10-08-linear-contour-index.md', '2026-10-08-whole-block.md', '2026-10-08-exit-preview.md', '2026-10-08-sample-layer.md', '2026-10-08-simple-device-table.md', 'automated-checks.json'):
        shutil.copy2(ROOT / 'tests/evidence' / filename, DEST / 'tests/evidence' / filename)
    for filename in ('2026-10-08-header-alignment.md', '2026-10-08-header-alignment.json',
                     '2026-10-08-free-end-gaps.md', '2026-10-08-free-end-gaps.json'):
        shutil.copy2(ROOT / 'tests/evidence' / filename, DEST / 'tests/evidence' / filename)
    for filename in ('05_常见错误原因与修复速查.md', '06_固定图块系统图与功率标注自动更新方案.md'):
        shutil.copy2(ROOT / 'docs' / filename, DEST / 'docs' / filename)
    for filename in ('2026-10-09-fixed-diagram.md', '2026-10-09-fixed-diagram.json',
                     '2026-10-09-panel-stringp-nil.md', '2026-10-09-template-choices.md',
                     '2026-10-09-post-stat-workflow.md', '2026-10-09-post-stat-workflow.json',
                     '2026-10-09-exit-devices.md', '2026-10-09-exit-devices.json',
                     '2026-10-09-circuit-preview.md', '2026-10-09-circuit-preview.json',
                     '2026-10-09-inline-power.md', '2026-10-09-device-thumbnails.md', '2026-10-09-panel-repairs.md', '2026-10-09-save-insert-037.md', '2026-10-09-save-insert-037.json',
                     '2026-10-09-store-parser-043.md', '2026-10-09-store-parser-043.json',
                     '2026-10-09-native-store-045.md', '2026-10-09-native-store-045.json',
                     '2026-10-09-store-readback-046.md', '2026-10-09-store-readback-046.json', '2026-10-09-cckk-generation-052.md', '2026-10-09-cckk-command-053.md', '2026-10-09-cckk-captions-054.md',
                     '2026-10-10-transaction-memory-055.md', '2026-10-10-direct-placement-056.md',
                     '2026-10-10-power-text-rollback-057.md', '2026-10-10-diagram-view-058.md',
                     '2026-10-10-deleted-diagram-059.md', '2026-10-10-device-contact-060.md', '2026-10-10-circuit-numbers-061.md', '2026-10-10-startup-062.md', '2026-10-10-auto-wire-063.md', '2026-10-10-auto-wire-063.json'):
        shutil.copy2(ROOT / 'tests/evidence' / filename, DEST / 'tests/evidence' / filename)
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-startup-064.md', DEST / 'tests/evidence/2026-10-10-startup-064.md')
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-startup-066.md', DEST / 'tests/evidence/2026-10-10-startup-066.md')
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-saved-records-067.md', DEST / 'tests/evidence/2026-10-10-saved-records-067.md')
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-circuit-colors-065.md', DEST / 'tests/evidence/2026-10-10-circuit-colors-065.md')
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-contact-exclusion-068.md', DEST / 'tests/evidence/2026-10-10-contact-exclusion-068.md')
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-concentrated-trunk-071.md', DEST / 'tests/evidence/2026-10-10-concentrated-trunk-071.md')
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-empty-pick-076.md', DEST / 'tests/evidence/2026-10-10-empty-pick-076.md')
    # Date: 2026-10-11. Keep the documentation tree after update notes moved.
    # The compatibility-specific loading guide above remains the package's guide.
    for source in sorted((ROOT / 'docs').rglob('*.md')):
        if source.name == '03_加载使用与验收说明.md':
            continue
        target = DEST / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for source in sorted((ROOT / 'tests/evidence').glob('2026-10-11-performance-*.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob('2026-10-11-performance-*.md')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob('2026-10-11-source-scan-*.*')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob('2026-10-11-empty-panel*096.*')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob('????-??-??-device-library-*.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob('????-??-??-recognition-preset-*.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-default-library-com-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-startup-com-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    shutil.copy2(ROOT / 'tests/evidence/2026-10-12-default-library-source.json',
                 DEST / 'tests/evidence/2026-10-12-default-library-source.json')
    for source in sorted((ROOT / 'tests/evidence').glob('????-??-??-gap-cross-circuit-[0-9][0-9][0-9].json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for pattern in ('????-??-??-large-xrecord-[0-9][0-9][0-9].json',
                    '????-??-??-large-xrecord-baseline.json',
                    '????-??-??-fallback-uuid-baseline-[0-9][0-9][0-9].json'):
        for source in sorted((ROOT / 'tests/evidence').glob(pattern)):
            shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-current-box-source-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-reachable-regression-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-contact-regression-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-placement-finish-checks-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-diagnostic-bundle-checks-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-system-block-library-checks-{PACKAGE_NO:03d}.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob(f'????-??-??-v{VERSION}-*.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    for source in sorted((ROOT / 'tests/evidence').glob('????-??-??-diagnostic-export-hang-analysis.json')):
        shutil.copy2(source, DEST / 'tests/evidence' / source.name)
    readme = guide
    (DEST / '使用说明.md').write_text(readme, encoding='utf-8')
    for filename in ('cad-plan.dxf', 'cad-plan.expected.json'):
        shutil.copy2(ROOT / 'tests/fixtures' / filename, DEST / 'tests/fixtures' / filename)
    # Date: 2026-10-15. Keep every dotted component of the software version.
    archive = DEST.parent / (DEST.name + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(DEST.rglob('*')):
            z.write(path, path.relative_to(DEST.parent))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for folder in ('config', 'output', 'templates'):
            assert f'{NAME}/{folder}/' in z.namelist()
        for name in z.namelist():
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                data = z.read(name)
                assert data.decode('gb2312').encode('gb2312') == data, name
                assert data == (DEST.parent / name).read_bytes(), name
    print(archive)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lite', action='store_true', help='Build the CADTools lite runtime')
    args = parser.parse_args()
    if args.lite:
        from cadtools_lite import build_lite
        build_lite()
    else:
        build()
