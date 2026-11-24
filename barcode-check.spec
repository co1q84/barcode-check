from pathlib import Path


project_dir = Path(SPECPATH).resolve()
app_icon = project_dir / "barcode_check" / "assets" / "app.ico"
analysis = Analysis(
    [str(project_dir / "barcode_check" / "__main__.py")],
    pathex=[str(project_dir)],
    datas=[(str(app_icon), "barcode_check/assets")],
)
archive = PYZ(analysis.pure)
exe = EXE(
    archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    name="条码厂商校验助手",
    console=False,
    upx=False,
    icon=str(app_icon),
)
