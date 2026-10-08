"""Build the AutoCAD 2020 trial package. Date: 2026-10-08."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NO = 14
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
    modules = ('common', 'config', 'geometry', 'topology', 'statistics', 'generation', 'main')
    update = (';; Date: 2026-10-08. Validate or initialize the plugin data root.\n'
              '(vl-load-com)\n' + '\n'.join(
                  (DEST / 'src' / f'{module}.lsp').read_bytes().decode('gb2312') for module in modules) +
              '\n(EL:ClearPickHighlights)\n(setq *EL:Result* nil)\n'
              '(if (EL:EnsureRoot)\n'
              f'  (princ "\\n已加载（CAD2020 v{PACKAGE_NO}）：目录已确认。输入 ELSETUP 或 ELSTAT 继续，已有有效图纸设置可沿用。")\n'
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
    for filename in ('2026-10-08-box-statistics.md', '2026-10-08-trace-diagnostics.md', '2026-10-08-contour-diagnostics.md', '2026-10-08-polyline-ocs-fix.md', 'automated-checks.json'):
        shutil.copy2(ROOT / 'tests/evidence' / filename, DEST / 'tests/evidence' / filename)
    readme = f'''# AutoCAD 2020 兼容试用包 v{PACKAGE_NO}
日期：2026-10-08
状态：源码、自动回归和编码检查完成；真实 CAD 全流程验收待执行

全部 LISP/DCL 使用严格 GB2312，文档使用 UTF-8。请完整解压，不直接加载仓库的 UTF-8 源码。

v14 根据 v13 实测日志修复多段线顶点转换路径：箱体 1FD6 内部轮廓 1DE0 的四次实体坐标转换均返回 nil，随后触发 numberp: nil。现使用 DXF 210 法向量指定 OCS，块插入变换仍只应用一次；转换返回无效点时立即停止并记录句柄、顶点、高程、法向量、目标坐标系和返回值。宿主回归已通过，实际 CAD 效果待原图复测。若仍失败，将命令行提示的 output/ELTRACE-debug.log 发回。即使目录不可写，也保留命令行失败上下文。日志追加保存，不修改图形。

1. 从旧 GB2312 包升级时，将旧包 config 中的 .eld 文件复制到新包 config；保留旧包作为备份。不要混用 UTF-8 配置。
2. APPLOAD 本包根目录的 START-CAD2020.lsp，选择本包内 src/load.lsp，确认 v{PACKAGE_NO}。也可用 {UPDATE_NAME} 更新内存代码，但它沿用已有有效目录，日志可能保存在旧目录；以命令行路径为准。
3. 运行 ELSTAT：拾取待统计箱体，再拾取该箱靠近出口的一段 LINE 或开放 LWPOLYLINE。无需先录入全部设备。
4. 集中核对出口表：勾选全部出线，取消进线。列表选择会高亮。需要其他导线图层时点“补充导线图层”；未纳入的箱边线须补充或明确排除，否则整箱未完成。
5. 未知类型在分类表按身份确认设备、配电箱、跨层引线或忽略；同名异定义／动态状态分开。未确认类型保留问题，取消不保存本次分类。
6. 功率窗口上方选择回路，下面按类型填写整数 W。每行点“保存此行”，最后 OK 应用到本图；仅显式勾选时另存设备库。0W 需要用途确认。
7. ELPOWER 可重改功率；ELISSUES 定位问题；ELSAVERESULT 保存当前有效结果。ELGEN 仍需真实系统图模板，未完成、冲突、缺功率或超过 172W 均不能生成。

设备内部端点和中段穿越接入内存拓扑，不切断 CAD 原线。接设备的整条导线均不搜索断口。断口继续使用 v10：默认 2000 mm、共线、相向、同高程、双向唯一。

封闭区域由可验证闭合轮廓形成，支持嵌套变换及受控圆弧离散。EL_HOLE 图层上的闭合轮廓可明确标记孔洞；无语义的嵌套闭环不会猜成孔洞或实心，报告 AMBIGUOUS_REGION。无可靠区域仅凭包围盒接近时报告待核对。其他不支持的实体保留诊断。

ELSETUP 仍可调整既有识别参数；ELGAPTEST 预览与 ELSTAT 整箱确认是不同操作。旧配置功率／模板保留，版本迁移会清理不兼容的旧断口配对并提示重核。

实际模型空间接线、DCL 显示／高亮、保存重开、真实动态块和大小图性能仍待 CAD 验收。阶段耗时与数量由 ELTRACE 输出并随结果保存。详细验收记录见 docs/03_加载使用与验收说明.md。
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
