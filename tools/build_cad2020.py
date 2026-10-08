"""Build the AutoCAD 2020 trial package. Date: 2026-10-08."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NO = 10
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

v10 当前规则：默认搜索 2000 mm。整条 LINE/LWPOLYLINE 任一端接了设备或配电箱，就不参与自动断口搜索；另一端也不会作为候选。只匹配共线、相向、同高程断口，忽略非共线交叉线，仅共线路径占用会阻止续接。采用端点和线段空间索引，完整检查搜索范围，不按最近距离提前认定连接。仅保留计算浮点尾差的内部精度余量，不提供断口偏移和角度容差调节。

第一次升级会将旧规则参数切换为 2000 mm 并要求重新核对，采样保留；在 ELSETUP 中保存后，后续沿用新规则下设置的搜索距离。ELGAPTEST 必须已有设备、配电箱及导线采样，缺少时先运行 ELSETUP（可保存草稿）。正常操作只需选断口；继续检查输入 N，选错端点输入 S，范围不够输入 R，看完回车退出。预览菜单已移除 P 高级参数。本次预览的范围调整不保存，正式统计在 ELSETUP 中设置并核对。

v9 历史变更（交互以 v10 为准）：ELGAPTEST 自动采用默认参数，新增 R（Range）单独修改搜索距离。

v8 补齐多段线导线及图块轮廓缺少标志字段时的默认值，避免空值进入位运算；增加 ELGAPTEST 完整命令回归及报错阶段、采集对象句柄提示。保留 v7 的 numberp: nil 修复。截图尚不能确定实际图纸的唯一根因，加载本包后请复测 ELGAPTEST；如仍报错，请保留包含失败阶段和对象信息的完整命令记录。

v7 修复 ELSTAT 选中配电箱后，对象快照处理空列表时触发 numberp: nil 的代码缺陷；类型、角色及可能为空的交互选项改用 EQUAL 比较。同步修复回车确认出线、退出断口预览及未配置设备类别时的同类问题。自动回归覆盖选择箱体到进入功率表，真实 CAD 图纸仍需复测。

v6 将 ELSETUP 的单位固定为 mm，取消单位输入和确认。参数选择改成中文数字提示：回车或输入 1 直接使用显示值，输入 2 才逐项调整。首次或改动后的参数，最后输入 1 表示已核对并启用统计；回车或输入 2 保存草稿。已有毫米配置的采样和参数未改变时，直接沿用确认结果，不再次询问。

v5 修复独立加载更新文件后，ELSETUP / ELSTAT 在拾取前出现 stringp nil 的问题。更新文件现在先确认完整插件目录，再显示可用提示；根目录为空、类型错误或已失效时，会请求选择本包内的 src/load.lsp。取消选择会停止本次操作，不会建立配置或继续拼接空路径。

拾取后的持续亮显与对象信息提示继续保留：采样、统计、断口/引线配对及模板采集中的对象都会亮显，直到当前命令完成或取消后清理。统计时选 Yes 的出线保持亮显，选 No 的候选取消亮显。图块可见性字段缺失修复也继续保留。

当前会话修复：解压完整包，APPLOAD 根目录的 {UPDATE_NAME}。如果弹出文件选择框，选择同一个包内的 src/load.lsp；看到“目录已确认”后运行 ELSETUP 或 ELSTAT，无需输入根目录命令。如果原 v2/v3/v4/v5 根目录仍完整有效，直接沿用原目录和已保存设置，不重复弹框；验证采样亮显时，在 ELSETUP 的已有采样提示中选择 Resample。若取消或选择不完整目录，会明确提示未就绪，下次命令仍可重新选择。

完整安装或切换到新包目录：

1. 将整个压缩包解压到新的、可写的目录。由本项目 GB2312 v2/v3/v4/v5 升级时，可以复制旧包 config 里的 .eld 文件到新包 config；同一 DWG 路径的有效采样和参数可沿用。不要复制原 UTF-8 版本的数据。
2. 打开 CAD，将新目录加入可信位置。在图纸副本上测试，并先保存为 DWG。
3. 执行 APPLOAD，加载新包根目录的 START-CAD2020.lsp。
4. 弹出文件选择框后，选择同一个新包内的 src/load.lsp。程序会自动设置根目录，替换旧包路径。
5. 命令行显示“已加载（CAD2020 v{PACKAGE_NO}）”后，有已确认的有效配置可直接运行 ELSTAT。首次使用则执行 ELSETUP，依次选择配电箱、导线、设备图块样本。单位固定为 mm，不会再询问。参数回车直接使用屏幕显示值，输入 2 才逐项调整；调整时各项回车保留当前值。
6. 首次或改动后的参数需要核对：最后回车或输入 2 保存草稿，再用 ELGAPTEST 检查典型断口、最大断口和邻近回路。确认正常接线的偏差可接受、应连接的断口对象正确且没有误选邻近回路后，重新运行 ELSETUP，回车沿用采样及参数，最后输入 1 启用统计。若沿用已确认且未改变的毫米配置，则不重复询问确认。
7. ELSETUP 只建立识别设置。显示“设置已确认并保存”后，输入 ELSTAT，选择待统计配电箱，按提示确认出线后进入功率表。

更新只替换当前 DWG 会话中的模块。重启 CAD 或换到另一个 DWG 后，重新加载本包。插件目录要完整保留，单个更新文件不能代替配置和界面目录。
tests/fixtures/cad-plan.dxf 是合成样图，v10 预期第一回路因接设备导线不续接而未完成，已识别负载为 5W、2W、5W，部分负载合计 12W，完整回路合计仅 7W，禁止生成；实际 CAD 导入及统计仍需验证。
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
        for name in z.namelist():
            if Path(name).suffix.lower() in ('.lsp', '.dcl'):
                data = z.read(name)
                assert data.decode('gb2312').encode('gb2312') == data, name
                assert data == (DEST.parent / name).read_bytes(), name
    print(archive)


if __name__ == '__main__':
    build()
