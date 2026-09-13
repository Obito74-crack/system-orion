"""Résolution homeDirectory/homeDrive (Active Directory) et impersonnification.

Cf. CDC EF-03 et D6 : accès réseau exclusivement sous l'identité de l'utilisateur
connecté (WTSQueryUserToken -> ImpersonateLoggedOnUser), jamais de compte de service.

TODO: ADSI via win32com (WinNT://domaine/utilisateur).
"""
