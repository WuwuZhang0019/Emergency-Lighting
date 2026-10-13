"""Build the AutoCAD 2020 trial package. Date: 2026-10-13."""
from pathlib import Path
import base64
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NO = 127
NAME = f'应急照明-{PACKAGE_NO:03d}'
UPDATE_NAME = f'UPDATE-{PACKAGE_NO:03d}.lsp'
DEST = ROOT / 'output' / NAME


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def lisp_string(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def embedded_resources():
    """Date: 2026-10-12. Fallback carries the same immutable default assets."""
    assets = sorted((DEST / 'src').glob('*.lsp')) + sorted((DEST / 'ui').glob('*'))
    writes = []
    for path in assets:
        if not path.is_file():
            continue
        lines = path.read_bytes().decode('gb2312').splitlines()
        payload = '\n'.join(lisp_string(line) for line in lines)
        relative = lisp_string(path.relative_to(DEST).as_posix())
        writes.append(f'(if (and ok (not (EL:StartupResource \'EL:StartupWriteLines (strcat root {relative})\n\'({payload})))) (setq ok nil))')
    for path in sorted((DEST / 'assets/default-device-library').rglob('*')):
        if not path.is_file():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        # Keep every literal below the legacy READ fragment limit.
        chunks = '\n'.join(lisp_string(encoded[i:i + 192]) for i in range(0, len(encoded), 192))
        relative = lisp_string(path.relative_to(DEST).as_posix())
        writes.append(f'(if (and ok (not (EL:StartupResource \'EL:StartupWriteBase64 (strcat root {relative})\n\'({chunks})))) (setq ok nil))')
    return ('(defun EL:StartupEmbeddedRoot (/ base root folder ok)\n'
            '  (if (setq base (EL:NormalizeRoot (getenv "LOCALAPPDATA")))\n'
            '    (progn\n'
            '      (setq base (strcat base "Emergency-Lighting/"))\n'
            '      (vl-mkdir base)\n'
            f'      (setq root (strcat base "runtime-{PACKAGE_NO:03d}/") ok T)\n'
            '      (vl-mkdir root)\n'
            '      (foreach folder \'("src" "ui" "config" "output" "templates")\n'
            '        (vl-mkdir (strcat root folder)))\n' + '\n'.join(writes) +
            f'\n      (if (and ok (EL:RootValid root)\n'
            f'        (EL:StartupWriteLines (strcat root "package-{PACKAGE_NO:03d}.marker") \'("Emergency-Lighting {PACKAGE_NO}"))) root))))\n')


def build():
    DEST.mkdir(exist_ok=True)
    for folder in ('src', 'ui', 'config', 'output', 'templates', 'docs', 'tests/fixtures'):
        (DEST / folder).mkdir(parents=True, exist_ok=True)
    # Formal seed assets are versioned source, separate from the mutable user library.
    defaults = ROOT / 'assets/default-device-library'
    assert (defaults / 'catalog.eld').is_file()
    assert len(list((defaults / 'assets').rglob('block.dwg'))) == 49
    assert len(list((defaults / 'assets').rglob('legend.sld'))) == 49
    shutil.copytree(defaults, DEST / 'assets/default-device-library', dirs_exist_ok=True)
    for folder, pattern in (('src', '*.lsp'), ('ui', '*.dcl')):
        for source in (ROOT / folder).glob(pattern):
            text = source.read_text(encoding='utf-8')
            if source.name == 'load.lsp':
                text = replace_once(text, '(if (and *EL:Root* (>= (getvar "LISPSYS") 1))', '(if *EL:Root*')
                text = replace_once(text, '需要 AutoCAD 2021+ Windows、LISPSYS=1/2（更改后重启）及完整插件目录。', '请选择本包的 src/load.lsp，并保留完整插件目录。')
                text = replace_once(text, '已加载：', f'已加载（CAD2020 v{PACKAGE_NO}）：')
            if source.name == 'config.lsp':
                text = replace_once(text, '(open path "r" "utf8")', '(open path "r")')
                text = replace_once(text, '(open tmp "w" "utf8")', '(open tmp "w")')
            if source.name == 'common.lsp':
                text = replace_once(text, '(open *EL:LogPath* "a" "utf8")', '(open *EL:LogPath* "a")')
                text = replace_once(text, '(open path "a" "utf8")', '(open path "a")')
                text = replace_once(text, 'AutoCAD 2021+, LISPSYS=1/2.', 'AutoCAD 2020 trial, GB2312 source and system-codepage data.')
            data = text.encode('gb2312', errors='strict')
            assert data.decode('gb2312') == text
            (DEST / folder / source.name).write_bytes(data)
    standalone = (DEST / 'src/insert-circuit.lsp').read_bytes() + f'\n(princ "\\nCCKK / CCKK1 / CCKK2 已加载（v{PACKAGE_NO}）：CCKK 回路，CCKK1 配电箱，CCKK2 整组箱体与回路。")\n(princ)\n'.encode('gb2312', errors='strict')
    (DEST / 'CCKK.lsp').write_bytes(standalone)
    shutil.copy2(ROOT / 'ui/box-ui-011.marker', DEST / 'ui/box-ui-011.marker')
    shutil.copy2(ROOT / 'ui/diagram-ui-044.marker', DEST / 'ui/diagram-ui-044.marker')
    marker = f"package-{PACKAGE_NO:03d}.marker"
    (DEST / marker).write_text(f"Emergency-Lighting {PACKAGE_NO}\n", encoding="ascii")
    # Keep an existing valid data root; initialize it for a standalone update.
    # All modules are included; readiness requires a complete package directory.
    modules = ('common', 'config', 'geometry', 'topology', 'statistics', 'device-library', 'device-assets', 'device-defaults', 'device-ui', 'device-recognition', 'device-inputs', 'device-migration', 'generation', 'main', 'simple', 'circuit-number', 'fixed', 'panel', 'store-compact', 'diagram-store', 'store-split', 'diagram-update', 'diagram-commands', 'insert-circuit', 'startup')
    module_texts = []
    for module in modules:
        text = (DEST / 'src' / f'{module}.lsp').read_bytes().decode('gb2312')
        if module == 'common':
            module_texts.append(text + '\n(EL:MonitorLoadBegin *EL:BootstrapTick*)\n')
        else:
            module_texts.append(f'(setq *EL:MonitorLabel* "{module}.lsp" *EL:LoadToken* (EL:PerfBegin "LOAD_MODULE"))\n'
                                + text + '\n(EL:PerfEnd *EL:LoadToken* \'returned)\n(setq *EL:MonitorLabel* nil)\n')
    update = (';; Date: 2026-10-13. Monitor APPLOAD from its first executable form.\n'
              '(setq *EL:BootstrapTick* (getvar "MILLISECS"))\n(vl-load-com)\n' + '\n'.join(module_texts) +
              '\n(EL:ClearPickHighlights)\n(setq *EL:Result* nil *EL:DeviceResult* nil)\n'
              f'(setq *EL:PackageMarker* "{marker}")\n'
              '(if (setq *EL:MonitorLoadReady* (EL:PerfCall "LOAD_ROOT" \'EL:EnsureRoot nil))\n'
              '  (progn (EL:PerfCall "LOAD_LIBRARY" \'EL:DLDefaultStartup nil)\n'
              f'    (princ "\\n已加载（CAD2020 v{PACKAGE_NO}）：目录已确认。输入 ELSTAT 开始统计。"))\n'
              f'  (princ "\\nCAD2020 v{PACKAGE_NO} 模块已载入，但未确认插件目录。运行 ELSETUP 或 ELSTAT 后选择完整包内的 src/load.lsp。"))\n'
              '(EL:MonitorLoadEnd (if *EL:MonitorLoadReady* \'load-finished \'load-failed))\n(princ)\n')
    (DEST / UPDATE_NAME).write_bytes(update.encode('gb2312'))
    # Date: 2026-10-10. Resolve APPLOAD folder, then validate version and assets.
    startup = replace_once(update, '(setq *EL:MonitorLoadReady* (EL:PerfCall "LOAD_ROOT" \'EL:EnsureRoot nil))',
                           f'(setq *EL:MonitorLoadReady* (EL:PerfCall "LOAD_ROOT" \'EL:StartupRoot (list "{marker}")))')
    startup = startup.replace('(if (setq *EL:MonitorLoadReady*', embedded_resources() + '\n(if (setq *EL:MonitorLoadReady*', 1)
    startup = startup.replace('运行 ELSETUP 或 ELSTAT 后选择完整包内的 src/load.lsp。',
                              '请根据上方具体错误修复后重新加载启动文件。')
    (DEST / 'START-CAD2020.lsp').write_bytes(startup.encode('gb2312', errors='strict'))
    (DEST / 'src/load.lsp').write_bytes(startup.encode('gb2312', errors='strict'))
    guide = (ROOT / 'docs/03_加载使用与验收说明.md').read_text(encoding='utf-8')
    guide = guide.replace('状态：源码及自动检查已交付，CAD 实测待执行。', f'状态：AutoCAD 2020 兼容试用包 v{PACKAGE_NO}，真实 CAD 验收待完成。')
    guide = guide.replace('目标为 Windows AutoCAD 2021+，`LISPSYS=1` 或 `2`（修改后需重启）', '本包供简体中文 Windows AutoCAD 2020 试用，LISP/DCL 已转换为 GB2312，无需设置 LISPSYS')
    guide = guide.replace('配置和结果使用 UTF-8 数据关联表', '本包配置和结果使用系统默认编码的数据关联表（简体中文 Windows 通常为 GBK），不要混用旧包配置')
    (DEST / 'docs/03_加载使用与验收说明.md').write_text(guide, encoding='utf-8')
    shutil.copy2(ROOT / 'docs/04_整箱自动分回路统计与设备功率赋值方案.md',
                 DEST / 'docs/04_整箱自动分回路统计与设备功率赋值方案.md')
    (DEST / 'tests/evidence').mkdir(exist_ok=True)
    for filename in ('2026-10-08-box-statistics.md', '2026-10-08-trace-diagnostics.md', '2026-10-08-contour-diagnostics.md', '2026-10-08-polyline-ocs-fix.md', '2026-10-08-curve-ocs-fix.md', '2026-10-08-region-performance.md', '2026-10-08-contact-performance.md', '2026-10-08-linear-contour-index.md', '2026-10-08-whole-block.md', '2026-10-08-exit-preview.md', '2026-10-08-sample-layer.md', '2026-10-08-simple-device-table.md', 'automated-checks.json'):
        shutil.copy2(ROOT / 'tests/evidence' / filename, DEST / 'tests/evidence' / filename)
    for filename in ('2026-10-08-header-alignment.md', '2026-10-08-header-alignment.json',
                     '2026-10-08-free-end-gaps.md', '2026-10-08-free-end-gaps.json'):
        shutil.copy2(ROOT / 'tests/evidence' / filename, DEST / 'tests/evidence' / filename)
    for filename in ('05_常见错误原因与修复速查.md', '06_固定图块系统图与功率标注自动更新方案.md', '00_面板保存记录.md'):
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
    readme = guide
    (DEST / '使用说明.md').write_text(readme, encoding='utf-8')
    for filename in ('cad-plan.dxf', 'cad-plan.expected.json'):
        shutil.copy2(ROOT / 'tests/fixtures' / filename, DEST / 'tests/fixtures' / filename)
    archive = DEST.with_suffix('.zip')
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
    build()
