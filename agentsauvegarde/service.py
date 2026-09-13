"""Point d'entrée du service Windows.

Cf. CDC section 5.1 (Composants logiciels) et section 7 (ET-03 - Cycle de fonctionnement) :
1. Démarrage : chargement configuration -> connexion base d'état -> dimensionnement USN -> boucle principale.
2. Boucle principale : lecture USN -> filtrage (EF-05) -> file -> VSS -> copie sous impersonnification -> MAJ USN traité.
3. Report sur verrouillage long ; files persistantes sur indisponibilité réseau (EF-12).
4. Tâches planifiées : rétention, rotation logs, contrôle espace cible.

TODO: implémenter via pywin32 (win32serviceutil.ServiceFramework).
"""
