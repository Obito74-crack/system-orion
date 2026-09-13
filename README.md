# System Orion

Agent Windows (service SYSTEM) sauvegardant silencieusement des arborescences
ciblées vers un partage réseau SMB, sans interaction utilisateur.

**Usage interne — projet propriétaire, ne pas redistribuer.**

## Documentation de référence

La spécification fonctionnelle et technique fait foi : [docs/CDC_SystemOrion_v1_3.md](docs/CDC_SystemOrion_v1_3.md)

Toute modification des décisions D1 à D11 du CDC exige une révision formelle
avant toute évolution du code correspondant.

**Important** : le déploiement en production, pilote inclus, est subordonné à
la validation du volet 9 du CDC (RGPD/AIPD) par un DPO ou juriste habilité (D9).
Ce dépôt ne préjuge pas de cette validation.

## Convention de nommage

| Usage | Valeur |
|---|---|
| Nom produit | System Orion |
| Service Windows (interne) | `SystemOrion` |
| Clé de registre | `HKLM\SOFTWARE\SystemOrion` |
| Source Event Log | `SystemOrion` |
| Dossier ProgramData | `C:\ProgramData\SystemOrion\logs` |
| Sous-dossier de sauvegarde réseau | `<homeDirectory>\SystemOrion\<NomPoste>` |
| Package Python | `systemorion` |

## Structure du projet

```
systemorion/
├── service.py          # Point d'entrée du service Windows « SystemOrion »
├── config.py           # Lecture/écriture de HKLM\SOFTWARE\SystemOrion
├── journal_usn.py       # Requête USN, filtrage, reprise, détection rotation
├── vss.py               # Clichés Win32_ShadowCopy
├── cible_ad.py          # Résolution homeDirectory/homeDrive, impersonnification
├── backup.py            # File de copie, versioning, reprise réseau, rétention
├── exclusions.py        # Évaluation des règles d'exclusion
├── logging_agent.py     # Event Log « SystemOrion » + fichiers rotatifs
└── state.py             # Persistance SQLite (USN, file d'attente, machine à états)
tests/                    # Tests unitaires et d'intégration (recette, section 10 du CDC)
docs/                      # Documents de référence (CDC, maquettes)
packaging/                 # Scripts PyInstaller / Inno Setup / MSI (ET-01)
```

## Environnement cible

Windows 10/11 (64 bits), Python 3.11+, domaine Active Directory. Voir CDC section 3.

## Installation (développement)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

## État du projet

Squelette initial — voir les `TODO` dans chaque module pour les blocs à implémenter,
dans l'ordre suggéré : `state.py` -> `config.py` -> `journal_usn.py` -> `vss.py` ->
`cible_ad.py` -> `exclusions.py` -> `backup.py` -> `logging_agent.py` -> `service.py`.
