"""Offline AutoCAD 2020 cold-recognition build. Date: 2026-10-23."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.84"
DLL_NAME = "EmergencyLighting.ColdRecognition84.dll"
TEST_NAME = "EmergencyLighting.ColdRecognition84.Tests.exe"
DEFAULT_OUTPUT = ROOT / "output" / "native-cold-v0.1.84"
CAD_VERSION = "23.1.0"
CAD_PACKAGES = {
    "AcMgd.dll": "autocad.net",
    "AcCoreMgd.dll": "autocad.net.core",
    "AcDbMgd.dll": "autocad.net.model",
}


class BuildError(Exception):
    def __init__(self, message, *, stage="configuration", stdout="", stderr=""):
        super().__init__(message)
        self.stage = stage
        self.stdout = stdout
        self.stderr = stderr


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def required_file(path, description):
    result = Path(path).expanduser().resolve()
    if not result.is_file():
        raise BuildError(f"{description}不存在：{result}")
    return result


def run_process(command, stage, *, input_text=None, timeout=120):
    try:
        result = subprocess.run(
            [str(part) for part in command], input=input_text, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            cwd=ROOT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BuildError(str(exc), stage=stage) from exc
    if result.returncode:
        raise BuildError(
            f"{stage}失败，退出码 {result.returncode}", stage=stage,
            stdout=result.stdout, stderr=result.stderr,
        )
    return result.stdout.strip()


def find_compiler(dotnet, requested):
    if requested:
        return required_file(requested, "C# 编译器")
    output = run_process([dotnet, "--list-sdks"], "locate-compiler")
    candidates = []
    for line in output.splitlines():
        match = re.fullmatch(r"([^ ]+) \[(.+)\]", line.strip())
        if match:
            version, directory = match.groups()
            compiler = Path(directory) / version / "Roslyn" / "bincore" / "csc.dll"
            if compiler.is_file():
                numeric = tuple(int(value) for value in re.findall(r"\d+", version))
                candidates.append((numeric, compiler))
    if not candidates:
        raise BuildError("未找到已安装的 Roslyn csc.dll；请使用 --csc 指定，不会联网安装")
    return max(candidates, key=lambda item: item[0])[1].resolve()


def reference_details(paths):
    """Read PE metadata only; never load an AutoCAD plug-in for execution."""
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise BuildError("缺少 Windows PowerShell，无法核对引用程序集版本")
    script = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$paths = ConvertFrom-Json -InputObject ([Console]::In.ReadToEnd())
$rows = @(foreach ($path in $paths) {
    $name = [System.Reflection.AssemblyName]::GetAssemblyName($path)
    $item = Get-Item -LiteralPath $path
    [pscustomobject]@{
        path = $item.FullName
        assembly_name = $name.Name
        assembly_version = $name.Version.ToString()
        file_version = $item.VersionInfo.FileVersion
    }
})
ConvertTo-Json -InputObject $rows -Compress
"""
    output = run_process(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        "reference-metadata", input_text=json.dumps([str(path) for path in paths]),
    )
    try:
        records = json.loads(output.lstrip("\ufeff"))
    except ValueError as exc:
        raise BuildError("引用程序集版本输出不是有效 JSON", stage="reference-metadata", stdout=output) from exc
    if not isinstance(records, list) or len(records) != len(paths):
        raise BuildError("引用程序集版本条目数量不一致", stage="reference-metadata")
    for record, path in zip(records, paths):
        record["sha256"] = sha256(path)
    return records


def build(output=DEFAULT_OUTPUT, *, test=False, csc=None, dotnet=None,
          framework_dir=None, nuget_root=None, acmgd=None, accoremgd=None,
          acdbmgd=None):
    dotnet = dotnet or os.environ.get("EL_COLD_DOTNET") or shutil.which("dotnet")
    if not dotnet:
        raise BuildError("未找到 dotnet；请通过 --dotnet 指定已安装的运行时，不会联网安装")
    compiler = find_compiler(dotnet, csc or os.environ.get("EL_COLD_CSC"))
    nuget = Path(nuget_root or os.environ.get("EL_COLD_NUGET_ROOT") or (Path.home() / ".nuget" / "packages")).resolve()
    framework = Path(framework_dir or os.environ.get("EL_COLD_FRAMEWORK_DIR") or (
        nuget / "microsoft.netframework.referenceassemblies.net47" / "1.0.3" / "build" / ".NETFramework" / "v4.7"
    )).resolve()
    references = [required_file(framework / name, ".NET 4.7 引用") for name in ("mscorlib.dll", "System.dll", "System.Core.dll")]
    if test:
        sources = sorted((ROOT / "native" / "ColdRecognition" / "Core").glob("*.cs"))
        sources += sorted((ROOT / "native" / "ColdRecognition.Tests").glob("*.cs"))
        name, target = TEST_NAME, "exe"
    else:
        overrides = {
            "AcMgd.dll": acmgd or os.environ.get("EL_COLD_ACMGD"),
            "AcCoreMgd.dll": accoremgd or os.environ.get("EL_COLD_ACCOREMGD"),
            "AcDbMgd.dll": acdbmgd or os.environ.get("EL_COLD_ACDBMGD"),
        }
        for name, package in CAD_PACKAGES.items():
            references.append(required_file(
                overrides[name] or nuget / package / CAD_VERSION / "lib" / "net47" / name,
                "AutoCAD 2020 引用",
            ))
        sources = sorted((ROOT / "native" / "ColdRecognition").rglob("*.cs"))
        name, target = DLL_NAME, "library"
    if not sources:
        raise BuildError("未找到要编译的 C# 源码")
    if test and not (ROOT / "native" / "ColdRecognition.Tests" / "Program.cs").is_file():
        raise BuildError("缺少原生核心测试入口 Program.cs")
    metadata = reference_details(references)
    if not test:
        for item in metadata[-3:]:
            if item["assembly_version"] != "23.1.0.0":
                raise BuildError(
                    f"要求 AutoCAD 2020 23.1.0.0 引用，实际 {item['assembly_name']}={item['assembly_version']}",
                    stage="reference-metadata",
                )
    destination = Path(output).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    artifact = destination / name
    command = [
        dotnet, compiler, "/noconfig", "/nostdlib+", "/nologo", "/utf8output",
        "/langversion:7.3", f"/target:{target}", "/platform:x64",
        "/deterministic+", "/optimize+", "/debug-", "/warn:4",
        f"/pathmap:{ROOT}=/_/Emergency-Lighting", f"/out:{artifact}",
    ]
    command += [f"/reference:{path}" for path in references]
    command += [str(path) for path in sources]
    compiler_output = run_process(command, "compile")
    result = {
        "date": "2026-10-22", "status": "passed", "version": VERSION,
        "mode": "core-tests" if test else "autocad-plugin", "framework": "net47",
        "platform": "x64", "language_version": "7.3", "deterministic": True,
        "offline": True, "autodesk_dlls_copied": False,
        "compiler": {"path": str(compiler), "sha256": sha256(compiler)},
        "references": metadata,
        "sources": [{"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)} for path in sources],
        "artifact": {"path": str(artifact), "bytes": artifact.stat().st_size, "sha256": sha256(artifact)},
        "compiler_output": compiler_output,
    }
    if test:
        test_output = run_process([artifact], "core-tests", timeout=60)
        try:
            result["tests"] = json.loads(test_output)
        except ValueError as exc:
            raise BuildError("核心测试未返回有效 JSON", stage="core-tests", stdout=test_output) from exc
        if not isinstance(result["tests"], dict) or result["tests"].get("status") != "passed":
            raise BuildError("核心测试未报告 passed", stage="core-tests", stdout=test_output)
    return result


def main():
    parser = argparse.ArgumentParser(description="离线编译 AutoCAD 2020 只读冷识别原型；不 restore、不下载、不复制 Autodesk DLL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="产物目录")
    parser.add_argument("--test", action="store_true", help="仅编译并运行不依赖 AutoCAD 的核心测试 EXE")
    for option, variable, description in (
        ("dotnet", "EL_COLD_DOTNET", "dotnet 可执行文件"),
        ("csc", "EL_COLD_CSC", "Roslyn csc.dll"),
        ("framework-dir", "EL_COLD_FRAMEWORK_DIR", ".NET Framework 4.7 引用目录"),
        ("nuget-root", "EL_COLD_NUGET_ROOT", "本地 NuGet 包缓存目录"),
        ("acmgd", "EL_COLD_ACMGD", "AutoCAD 2020 AcMgd.dll"),
        ("accoremgd", "EL_COLD_ACCOREMGD", "AutoCAD 2020 AcCoreMgd.dll"),
        ("acdbmgd", "EL_COLD_ACDBMGD", "AutoCAD 2020 AcDbMgd.dll"),
    ):
        parser.add_argument("--" + option, help=f"{description}；也可设置 {variable}")
    args = parser.parse_args()
    try:
        result = build(**vars(args))
    except BuildError as exc:
        print(json.dumps({"status": "failed", "stage": exc.stage, "error": str(exc), "stdout": exc.stdout, "stderr": exc.stderr}, ensure_ascii=False))
        return 1
    except OSError as exc:
        print(json.dumps({"status": "failed", "stage": "filesystem", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
