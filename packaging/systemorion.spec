# -*- mode: python ; coding: utf-8 -*-
"""Spécification PyInstaller pour System Orion (CDC ET-01).

Génère une distribution "one-dir" contenant :
1. SystemOrionService.exe : Service Windows principal exécuté en SYSTEM (service.py)
2. SystemOrionAdmin.exe : Panneau de configuration graphique administrateur Qt6 (gui/main_window.py)
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collecte des modules et ressources nécessaires
hidden_imports_service = [
    "win32service",
    "win32serviceutil",
    "win32event",
    "win32file",
    "win32security",
    "win32ts",
    "win32evtlog",
    "win32evtlogutil",
    "win32con",
    "winerror",
    "win32com",
    "win32com.client",
    "systemorion",
    "systemorion.models",
    "systemorion.state",
    "systemorion.config",
    "systemorion.journal_usn",
    "systemorion.vss",
    "systemorion.cible_ad",
    "systemorion.exclusions",
    "systemorion.backup",
    "systemorion.logging_agent",
    "systemorion.service",
]

hidden_imports_gui = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "systemorion.gui",
    "systemorion.gui.main_window",
    "systemorion.gui.theme",
]

# Analyse du service Windows
a_service = Analysis(
    ["../systemorion/service.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports_service,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_service = PYZ(
    a_service.pure,
    a_service.zipped_data,
    cipher=block_cipher,
)

exe_service = EXE(
    pyz_service,
    a_service.scripts,
    [],
    exclude_binaries=True,
    name="SystemOrionService",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Analyse du panneau de configuration d'administration (GUI)
a_gui = Analysis(
    ["../systemorion/gui/main_window.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports_service + hidden_imports_gui,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz_gui = PYZ(
    a_gui.pure,
    a_gui.zipped_data,
    cipher=block_cipher,
)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="SystemOrionAdmin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Assemblage du dossier collectif 'one-dir'
coll = COLLECT(
    exe_service,
    a_service.binaries,
    a_service.zipfiles,
    a_service.datas,
    exe_gui,
    a_gui.binaries,
    a_gui.zipfiles,
    a_gui.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SystemOrion",
)
