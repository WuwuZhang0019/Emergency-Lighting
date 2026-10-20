"""CADTools runtime manifest and optional delivery writer. Date: 2026-10-20."""
from pathlib import Path
import re
import zipfile

import build_cad2020 as full


def version():
    return f'lite-v{full.VERSION}'


def runtime_text(source):
    """Keep business code shared; only redirect mutable paths for installed use."""
    text = full.cad2020_bytes(source).decode('gb2312')
    text = re.sub(r'\(strcat \*EL:Root\* "(config/|output(?:/|"))',
                  r'(strcat *EL:LiteDataRoot* "\1', text)
    if source.name == 'config.lsp':
        text = full.replace_once(text, '(strcat root "config/drawing-"',
                                 '(strcat *EL:LiteDataRoot* "config/drawing-"')
        text = full.replace_once(text, "(foreach folder '(\"config\" \"output\" \"templates\")",
                                 "(foreach folder '(\"templates\")")
        text = full.replace_once(text, '(and ok (EL:BoxUIValid root))',
                                 '(and ok (findfile (strcat root *EL:LiteMarker*)) (EL:BoxUIValid root))')
        text = text.replace('src、ui、config、output、templates', 'src、ui、assets、templates')
    return text


def runtime_files():
    """Assemble bytes in memory; does not create output directories or archives."""
    files = {}
    for source in sorted((full.ROOT / 'src').glob('*.lsp')):
        if source.name != 'load.lsp':
            files[f'src/{source.name}'] = runtime_text(source).encode('gb2312', errors='strict')
    for source in sorted((full.ROOT / 'ui').iterdir()):
        if source.is_file() and source.suffix in ('.dcl', '.marker'):
            files[f'ui/{source.name}'] = (full.cad2020_bytes(source)
                                         if source.suffix == '.dcl' else source.read_bytes())
    defaults = full.ROOT / 'assets/default-device-library'
    assert (defaults / 'catalog.eld').is_file()
    assert len(list(defaults.rglob('block.dwg'))) == 49
    assert len(list(defaults.rglob('legend.sld'))) == 49
    for source in sorted(defaults.rglob('*')):
        if source.is_file() and source.suffix in ('.eld', '.dwg', '.sld'):
            files[source.relative_to(full.ROOT).as_posix()] = source.read_bytes()
    template = full.ROOT / 'templates/系统图块库.dwg'
    data = template.read_bytes()
    assert data[:6] in (b'AC1015', b'AC1018', b'AC1021', b'AC1024', b'AC1027', b'AC1032')
    files['templates/系统图块库.dwg'] = data
    marker = f'{version()}.marker'
    files[marker] = f'Emergency-Lighting {version()} package-{full.PACKAGE_NO:03d}\n'.encode('ascii')
    test_entry = (full.ROOT / 'tools/templates/cadtools-lite-test.lsp').read_text(encoding='utf-8')
    files['ELTEST.lsp'] = test_entry.replace('@VERSION@', version()).replace('@MARKER@', marker).encode('gb2312', errors='strict')
    # Startup and batch numbering are retained, including every public command.
    modules = (*full.MODULES, 'batch-number')
    # One trusted entry, like the full edition: no per-module LOAD/security dialogs.
    # Keep module files for diagnostics; embed exactly the same converted bytes.
    module_code = []
    for module in modules:
        text = files[f'src/{module}.lsp'].decode('gb2312')
        if module == 'common':
            module_code.append(text + '\n(EL:MonitorLoadBegin *EL:BootstrapTick*)\n'
                               '(setq *EL:LiteMonitorStarted* T)\n')
        else:
            module_code.append(
                f'(setq *EL:MonitorLabel* "{module}.lsp" token (EL:PerfBegin "LOAD_MODULE"))\n'
                + text + "\n(EL:PerfEnd token 'returned) (setq *EL:MonitorLabel* nil)\n")
    loader = (full.ROOT / 'tools/templates/cadtools-lite-load.lsp').read_text(encoding='utf-8')
    for key, value in {
        '@VERSION@': version(),
        '@MARKER@': marker,
        '@FILES@': '\n    '.join(full.lisp_string(name) for name in sorted((*files, 'src/load.lsp'))),
        '@MODULE_CODE@': '\n'.join(module_code),
    }.items():
        loader = loader.replace(key, value)
    files['src/load.lsp'] = loader.encode('gb2312', errors='strict')
    guide = (full.ROOT / 'docs/CADTools精简运行版.md').read_text(encoding='utf-8')
    files['使用说明.md'] = guide.replace('版本：与完整版同步', f'版本：{version()}').encode('utf-8')
    return files


def build_lite():
    """Only called by an explicitly requested --lite build; never builds full first."""
    name = f'应急照明-{version()}'
    destination = full.OUTPUT_ROOT / name
    archive = full.OUTPUT_ROOT / f'{name}.zip'
    assert destination.resolve().parent == full.OUTPUT_ROOT.resolve()
    # Never erase an existing installation or its user-created files on a rebuild.
    if destination.exists() or archive.exists():
        raise FileExistsError(f'目标已存在，请先另行保留：{destination} / {archive}')
    files = runtime_files()
    for relative, data in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as packed:
        for relative, data in files.items():
            packed.writestr(f'{name}/{relative}', data)
    with zipfile.ZipFile(archive) as packed:
        assert packed.testzip() is None
        for relative, data in files.items():
            assert (destination / relative).read_bytes() == packed.read(f'{name}/{relative}') == data
            if Path(relative).suffix in ('.lsp', '.dcl'):
                assert data.decode('gb2312').encode('gb2312') == data
    print(f'{archive}\n{len(files)} files, {sum(map(len, files.values()))} bytes')
