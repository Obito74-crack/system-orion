"""Création/suppression de clichés Win32_ShadowCopy (VSS).

Cf. CDC EF-06 et section 8 (vssadmin indisponible sur Windows 11 -> WMI uniquement).
Un seul cliché à la fois ; suppression garantie (try/finally).

TODO: appel WMI Win32_ShadowCopy.Create via win32com.
"""
