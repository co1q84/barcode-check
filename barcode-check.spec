from pathlib import Path


project_dir = Path(SPECPATH).resolve()
analysis = Analysis(
    [str(project_dir / "barcode_check" / "__main__.py")],
    pathex=[str(project_dir)],
)
archive = PYZ(analysis.pure)
exe = EXE(
    archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    name="barcode-check",
    console=False,
    upx=False,
    icon="NONE",
)
