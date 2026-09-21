#!/usr/bin/env python3
"""Script d'orchestration de compilation et packaging pour System Orion (CDC ET-01, ET-04).

Étapes exécutées :
1. Compilation PyInstaller (distribution one-dir : Service + Admin GUI)
2. Signature numérique optionnelle des binaires (D10 / ET-04)
3. Compilation Inno Setup (.exe d'installation silencieuse /VERYSILENT)
4. Compilation WiX Toolset (.msi pour déploiement GPO)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = PROJECT_ROOT / "packaging"
DIST_DIR = PROJECT_ROOT / "dist"
OUTPUT_DIR = PACKAGING_DIR / "output"


def run_command(cmd: list[str], cwd: Path, desc: str) -> None:
    """Exécute une commande shell et affiche les messages d'état."""
    print(f"==> [{desc}] : {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERREUR lors de {desc} (code {result.returncode}) :", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    print(f"OK : {desc} terminé avec succès.")


def build_pyinstaller() -> None:
    """Compile le binaire one-dir avec PyInstaller."""
    spec_file = PACKAGING_DIR / "systemorion.spec"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file),
    ]
    run_command(cmd, PROJECT_ROOT, "Compilation PyInstaller (Service + GUI)")


def sign_binaries(cert_path: str, cert_pass: str) -> None:
    """Signe les binaires générés avec signtool (CDC D10, ET-04)."""
    signtool = shutil.which("signtool.exe") or r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"
    if not os.path.exists(signtool) and not shutil.which("signtool"):
        print("AVERTISSEMENT : signtool.exe introuvable. Étape de signature ignorée.")
        return

    bin_dir = DIST_DIR / "SystemOrion"
    files_to_sign = [
        bin_dir / "SystemOrionService.exe",
        bin_dir / "SystemOrionAdmin.exe",
    ]

    for f in files_to_sign:
        if f.exists():
            cmd = [
                signtool,
                "sign",
                "/f", cert_path,
                "/p", cert_pass,
                "/tr", "http://timestamp.digicert.com",
                "/td", "sha256",
                "/fd", "sha256",
                str(f),
            ]
            run_command(cmd, PROJECT_ROOT, f"Signature de {f.name}")


def build_inno_setup() -> None:
    """Compile l'installateur Inno Setup."""
    iscc = shutil.which("ISCC.exe") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    iss_file = PACKAGING_DIR / "installer.iss"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(iscc) and not shutil.which("ISCC"):
        print("AVERTISSEMENT : Compilateur Inno Setup (ISCC) introuvable. Étape ignorée.")
        return

    cmd = [str(iscc), f"/O{OUTPUT_DIR}", str(iss_file)]
    run_command(cmd, PACKAGING_DIR, "Création de l'installateur Inno Setup (.exe)")


def build_wix_msi() -> None:
    """Compile le package MSI avec WiX Toolset."""
    candle = shutil.which("candle.exe")
    light = shutil.which("light.exe")
    wxs_file = PACKAGING_DIR / "systemorion.wxs"

    if not candle or not light:
        print("AVERTISSEMENT : WiX Toolset (candle/light) introuvable. Étape MSI ignorée.")
        return

    obj_file = PACKAGING_DIR / "systemorion.wixobj"
    msi_file = OUTPUT_DIR / "SystemOrion_0.1.0.msi"

    run_command([candle, "-arch", "x64", str(wxs_file), "-o", str(obj_file)], PACKAGING_DIR, "WiX Candle")
    run_command([light, "-ext", "WixUIExtension", str(obj_file), "-o", str(msi_file)], PACKAGING_DIR, "WiX Light")


def main() -> None:
    parser = argparse.ArgumentParser(description="System Orion Build & Packaging Orchestrator")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Ignorer la passe PyInstaller")
    parser.add_argument("--skip-inno", action="store_true", help="Ignorer l'installateur Inno Setup")
    parser.add_argument("--skip-msi", action="store_true", help="Ignorer le package MSI GPO")
    parser.add_argument("--cert-file", type=str, default=None, help="Chemin vers le certificat PFX de signature de code")
    parser.add_argument("--cert-pass", type=str, default=None, help="Mot de passe du certificat de signature")

    args = parser.parse_args()

    print("==================================================")
    print("   System Orion — Chaîne de Packaging (ET-01)    ")
    print("==================================================")

    if not args.skip_pyinstaller:
        build_pyinstaller()

    if args.cert_file and args.cert_pass:
        sign_binaries(args.cert_file, args.cert_pass)

    if not args.skip_inno:
        build_inno_setup()

    if not args.skip_msi:
        build_wix_msi()

    print("\nProcessus de packaging terminé avec succès !")


if __name__ == "__main__":
    main()
