"""Build the AutoCAD 2020 trial package. Date: 2026-10-11."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NO = 81
NAME = f'应急照明-{PACKAGE_NO:03d}'
UPDATE_NAME = f'UPDATE-{PACKAGE_NO:03d}.lsp'
DEST = ROOT / 'output' / NAME


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def lisp_string(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def embedded_resources():
    """Date: 2026-10-10. Portable fallback; never overwrite config or output."""
    assets = sorted((DEST / 'src').glob('*.lsp')) + sorted((DEST / 'ui').glob('*'))
    writes = []
    for path in assets:
        if not path.is_file():
            continue
        lines = path.read_bytes().decode('gb2312').splitlines()
        payload = '\n'.join(lisp_string(line) for line in lines)
        relative = lisp_string(path.relative_to(DEST).as_posix())
        writes.append(f'(if (not (EL:StartupWriteLines (strcat root {relative})\n\'({payload}))) (setq ok nil))')
    return ('(defun EL:StartupEmbeddedRoot (/ base root folder ok)\n'
            '  (if (setq base (EL:NormalizeRoot (getenv "LOCALAPPDATA")))\n'
            '    (progn\n'
            '      (setq base (strcat base "Emergency-Lighting/"))\n'
            '      (vl-mkdir base)\n'
            f'      (setq root (strcat base "runtime-{PACKAGE_NO:03d}/") ok T)\n'
            '      (vl-mkdir root)\n'
            '      (foreach folder \'("src" "ui" "config" "output" "templates")\n'
            '        (vl-mkdir (strcat root folder)))\n' + '\n'.join(writes) +
            '\n      (if (and ok (EL:RootValid root)) root))))\n')


def build():
    DEST.mkdir(exist_ok=True)
    for folder in ('src', 'ui', 'config', 'output', 'templates', 'docs', 'tests/fixtures'):
        (DEST / folder).mkdir(parents=True, exist_ok=True)
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
    modules = ('common', 'config', 'geometry', 'topology', 'statistics', 'generation', 'main', 'simple', 'fixed', 'panel', 'diagram-store', 'diagram-update', 'diagram-commands', 'insert-circuit', 'startup')
    update = (';; Date: 2026-10-10. Validate or initialize the plugin data root.\n'
              '(vl-load-com)\n' + '\n'.join(
                  (DEST / 'src' / f'{module}.lsp').read_bytes().decode('gb2312') for module in modules) +
              '\n(EL:ClearPickHighlights)\n(setq *EL:Result* nil *EL:DeviceResult* nil)\n'
              f'(setq *EL:PackageMarker* "{marker}")\n'
              '(if (EL:EnsureRoot)\n'
              f'  (princ "\\n已加载（CAD2020 v{PACKAGE_NO}）：目录已确认。输入 ELSTAT 开始统计。")\n'
              f'  (princ "\\nCAD2020 v{PACKAGE_NO} 模块已载入，但未确认插件目录。运行 ELSETUP 或 ELSTAT 后选择完整包内的 src/load.lsp。"))\n'
              '(princ)\n')
    (DEST / UPDATE_NAME).write_bytes(update.encode('gb2312'))
    # Date: 2026-10-10. Resolve APPLOAD folder, then validate version and assets.
    startup = f'(if (EL:StartupRoot "{marker}")'.join(update.rsplit('(if (EL:EnsureRoot)', 1))
    startup = startup.replace('(if (EL:StartupRoot', embedded_resources() + '\n(if (EL:StartupRoot', 1)
    startup = startup.replace('运行 ELSETUP 或 ELSTAT 后选择完整包内的 src/load.lsp。',
                              '请检查本地数据目录写入权限后重新加载启动文件。')
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
    shutil.copy2(ROOT / 'docs/2026-10-10-解析圆与圆弧识别-074.md', DEST / 'docs/2026-10-10-解析圆与圆弧识别-074.md')
    shutil.copy2(ROOT / 'tests/evidence/2026-10-10-empty-pick-076.md', DEST / 'tests/evidence/2026-10-10-empty-pick-076.md')
    shutil.copy2(ROOT / "docs/2026-10-10-独立图例预览-078.md", DEST / "docs/2026-10-10-独立图例预览-078.md")
    shutil.copy2(ROOT / 'docs/2026-10-10-回路漏识别与生成诊断-079.md', DEST / 'docs/2026-10-10-回路漏识别与生成诊断-079.md')
    shutil.copy2(ROOT / 'docs/2026-10-11-宽导线接触与预览避色-080.md', DEST / 'docs/2026-10-11-宽导线接触与预览避色-080.md')
    shutil.copy2(ROOT / 'docs/2026-10-11-首次打开保存记录-081.md', DEST / 'docs/2026-10-11-首次打开保存记录-081.md')
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
