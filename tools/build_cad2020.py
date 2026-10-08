"""Build the AutoCAD 2020 trial package. Date: 2026-10-08."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NO = 24
NAME = f'应急照明-{PACKAGE_NO:03d}'
UPDATE_NAME = f'UPDATE-{PACKAGE_NO:03d}.lsp'
DEST = ROOT / 'output' / NAME


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


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
    shutil.copy2(ROOT / 'ui/box-ui-011.marker', DEST / 'ui/box-ui-011.marker')
    launcher = ''';; Date: 2026-10-08. Select this package's src/load.lsp explicitly.
(vl-load-com)
(defun EL2020:Start (/ selected)
  (setq selected (getfiled "请选择新包内的 src/load.lsp" "" "lsp" 0))
  (if selected
    (progn
      (setq *EL:Root* (strcat (vl-filename-directory selected) "/../"))
      (load selected)))
  (princ))
(EL2020:Start)
(princ)
'''
    (DEST / 'START-CAD2020.lsp').write_bytes(launcher.encode('gb2312'))
    # Keep an existing valid data root; initialize it for a standalone update.
    # All modules are included; readiness requires a complete package directory.
    modules = ('common', 'config', 'geometry', 'topology', 'statistics', 'generation', 'main', 'simple')
    update = (';; Date: 2026-10-08. Validate or initialize the plugin data root.\n'
              '(vl-load-com)\n' + '\n'.join(
                  (DEST / 'src' / f'{module}.lsp').read_bytes().decode('gb2312') for module in modules) +
              '\n(EL:ClearPickHighlights)\n(setq *EL:Result* nil *EL:DeviceResult* nil)\n'
              '(if (EL:EnsureRoot)\n'
              f'  (princ "\\n已加载（CAD2020 v{PACKAGE_NO}）：目录已确认。输入 ELSTAT，拾取配电箱和导线后填写设备功率。")\n'
              f'  (princ "\\nCAD2020 v{PACKAGE_NO} 模块已载入，但未确认插件目录。运行 ELSETUP 或 ELSTAT 后选择完整包内的 src/load.lsp。"))\n'
              '(princ)\n')
    (DEST / UPDATE_NAME).write_bytes(update.encode('gb2312'))
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
    readme = f'''# AutoCAD 2020 兼容试用包 v{PACKAGE_NO}
日期：2026-10-08
状态：源码、自动回归和编码检查完成；真实 CAD 全流程验收待执行

全部 LISP/DCL 使用严格 GB2312，文档使用 UTF-8。请完整解压，不直接加载仓库的 UTF-8 源码。

v24 修复接过配电箱或设备的导线在断口处停止统计的问题：按断口端点是否悬空判断续接，不再因导线另一端或中段接设备而排除整条导线。保留两次拾取、功率记忆和表头对齐。

1. 从旧 GB2312 包升级时，将旧包 config 中的 .eld 文件复制到新包 config；保留旧包作为备份。不要混用 UTF-8 配置。
2. APPLOAD 本包根目录的 START-CAD2020.lsp，选择本包内 src/load.lsp，确认 v{PACKAGE_NO}。请完整加载新包，避免读取旧目录的界面或设置。
3. 运行 ELSTAT：拾取配电箱，再拾取该系统任意一段 LINE 或开放 LWPOLYLINE，导线仅用于确定图层。无需运行 ELSETUP，不用选择出线、设备图层或设备类别。
4. 设备表三列为“设备图块／数量／单个功率（W）”。首次填写各图块的单个整数 W，点“保存并关闭”，下次自动带入。数量由程序统计。

点选设备行或“在图上查看该设备”，会暂时关闭表格，缩放至该类设备并亮显、加黄色框。按 Enter 返回表格，已输入的功率保留。切换行会保留输入，无需逐行点保存。取消不写功率文件。

功率自动保存在本包 config/block-powers.eld，同名图块沿用同一功率，跨图纸也可复用。更换交付目录时保留并复制该文件。旧版按角色／图纸保存的功率不自动转换；首次使用本表需录入一次。0W 可以保存，不预设灯具默认功率。

范围为所选配电箱通过所选导线图层连接到的设备；选中箱体之外的连通图块全部视为设备，同层但不连通的不计入。每个图块只按整体包围盒识别，端点落入或导线中段穿过都算接入，不扫描内部线、圆弧或嵌套块。T 接自动连通，单纯导线中段交叉不自动并线。悬空直线断口在 2000 mm 内按共线、相向、同高程、双向唯一规则自动续接；端点已接线或落在设备范围内的不续接，不能跨越断口中的设备或同路径导线。连续多个明确断口也可接入统计，不补画或修改原导线。

只改功率可运行 ELPOWER；改动接线、增删设备后重新运行 ELSTAT。该表汇总整个系统的设备，不用于逐回路 172W 判断或直接 ELGEN。需要原高级分回路流程时单独使用 ELTRACE，旧命令仍保留。

真实 CAD 的表格显示、缩放亮显、数量准确性和执行耗时待实测，尚不能承诺秒级。诊断版本为 024；日志路径在命令行显示，通常为本包 output/ELTRACE-debug.log。日志记录断口坐标、方向、候选／拒绝理由及续接数量，最多详细记录 100 个悬空端点，并标明省略数量。v24 专项记录见 tests/evidence/2026-10-08-free-end-gaps.md。
'''
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
