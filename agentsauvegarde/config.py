"""Lecture/écriture du magasin de configuration unique.

Cf. CDC D7 : magasin unique (registre HKLM\\SOFTWARE\\AgentSauvegarde) alimenté
soit par l'assistant manuel (EF-01/EF-01a), soit par GPO (EF-02, modèle ADMX).
Doit exposer un indicateur ManagedByGpo pour le verrouillage de l'UI (EF-01a).

TODO: implémenter lecture/écriture registre (winreg / pywin32).
"""
