"""Build the AutoCAD 2020 trial package. Date: 2026-10-08."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NO = 5
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
                text = replace_once(text, 'AutoCAD 2021+, LISPSYS=1/2.', 'AutoCAD 2020 trial, GB2312 source and system-codepage data.')
            data = text.encode('gb2312', errors='strict')
            assert data.decode('gb2312') == text
            (DEST / folder / source.name).write_bytes(data)
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
    readme = f'''# AutoCAD 2020 兼容试用包 v{PACKAGE_NO}
日期：2026-10-08
状态：已完成兼容打包，真实 CAD 全流程验收待完成

适用于简体中文 Windows 上的 AutoCAD 2020。全部 LISP 和 DCL 已转换为 GB2312，无需自行改编码或设置 LISPSYS。文档保持 UTF-8。

v5 修复独立加载更新文件后，ELSETUP / ELSTAT 在拾取前出现 stringp nil 的问题。更新文件现在先确认完整插件目录，再显示可用提示；根目录为空、类型错误或已失效时，会请求选择本包内的 src/load.lsp。取消选择会停止本次操作，不会建立配置或继续拼接空路径。

拾取后的持续亮显与对象信息提示继续保留：采样、统计、断口/引线配对及模板采集中的对象都会亮显，直到当前命令完成或取消后清理。统计时选 Yes 的出线保持亮显，选 No 的候选取消亮显。图块可见性字段缺失修复也继续保留。

当前会话修复：解压完整包，APPLOAD 根目录的 {UPDATE_NAME}。如果弹出文件选择框，选择同一个包内的 src/load.lsp；看到“目录已确认”后运行 ELSETUP 或 ELSTAT，无需输入根目录命令。如果原 v2/v3/v4 根目录仍完整有效，直接沿用原目录和已保存设置，不重复弹框；验证采样亮显时，在 ELSETUP 的已有采样提示中选择 Resample。若取消或选择不完整目录，会明确提示未就绪，下次命令仍可重新选择。

完整安装或切换到新包目录：

1. 将整个压缩包解压到新的、可写的目录。由本项目 GB2312 v2/v3/v4 升级时，可以复制旧包 config 里的 .eld 文件到新包 config；同一 DWG 路径的有效采样和参数可沿用。不要复制原 UTF-8 版本的数据。
2. 打开 CAD，将新目录加入可信位置。在图纸副本上测试，并先保存为 DWG。
3. 执行 APPLOAD，加载新包根目录的 START-CAD2020.lsp。
4. 弹出文件选择框后，选择同一个新包内的 src/load.lsp。程序会自动设置根目录，替换旧包路径。
5. 命令行显示“已加载（CAD2020 v{PACKAGE_NO}）”后，有已确认的有效配置可直接运行 ELSTAT。首次使用则执行 ELSETUP，依次选择配电箱、导线、设备图块样本。图纸实际单位为毫米时回车采用 mm，参数回车采用屏幕显示的建议值，无需逐项输入。
6. 最后选 No 或回车会保存未校准草稿，并显示下一步。可用 ELGAPTEST 试查；核对真实接线误差、断口和相邻回路后，再次运行 ELSETUP，回车沿用采样及参数，最后选 Yes。只有确认校准后才可用 ELSTAT 统计。
7. ELSETUP 只建立识别设置。显示“设置已确认并保存”后，输入 ELSTAT，选择待统计配电箱，按提示确认出线后进入功率表。

更新只替换当前 DWG 会话中的模块。重启 CAD 或换到另一个 DWG 后，重新加载本包。插件目录要完整保留，单个更新文件不能代替配置和界面目录。
tests/fixtures/cad-plan.dxf 是合成样图，预期回路功率为 10W、2W、5W，总计 17W；实际 CAD 导入及统计仍需验证。
详细命令顺序见 docs/03_加载使用与验收说明.md。系统图生成还需用真实动态块执行 ELTEMPLATE。

本包取消了 LISPSYS 入口限制，并将配置读写改为旧版两参数 open 接口。配置使用系统默认编码；勿与 UTF-8 版本混用数据。本包尚未通过 AutoCAD 2020 全流程实测。
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
    print(archive)


if __name__ == '__main__':
    build()
