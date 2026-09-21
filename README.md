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
├── config.py           # Lecture/écriture de HKLM\SOFTWARE\SystemOrion et GPO Policies
├── journal_usn.py       # Requête USN, filtrage, reprise, détection rotation
├── vss.py               # Clichés Win32_ShadowCopy
├── cible_ad.py          # Résolution homeDirectory/homeDrive, impersonnification
├── backup.py            # File de copie, versioning, reprise réseau, rétention
├── exclusions.py        # Évaluation des règles d'exclusion
├── logging_agent.py     # Event Log « SystemOrion » + fichiers rotatifs
├── models.py            # Modèles de données, énumérations et exceptions
├── state.py             # Persistance SQLite (USN, file d'attente, machine à états)
└── gui/                 # Interface d'administration Qt6 / PySide6 (EF-01a)
    ├── main_window.py   # Navigation à deux écrans (Dashboard & Dossiers)
    └── theme.py         # Thème visuel et styles QSS
gpo/                     # Modèles d'administration Active Directory (EF-02)
├── SystemOrion.admx     # Fichier de modèle ADMX
└── fr-FR/
    └── SystemOrion.adml # Fichier de localisation ADML
packaging/               # Packaging et déploiement (ET-01, EF-01, EF-02, EF-11)
├── build.py             # Script orchestrateur de compilation et signature Authenticode
├── installer.iss        # Installateur Inno Setup (.exe)
├── systemorion.wxs      # Paquet MSI WiX Toolset (.msi)
└── systemorion.spec     # Configuration multi-binaires PyInstaller
tests/                   # Tests unitaires et de régression (recette, section 10 du CDC)
docs/                    # Documents de référence (CDC v1.3, maquettes)
.github/workflows/       # Pipeline d'intégration continue CI/CD GitHub Actions
```

## Environnement cible

Windows 10/11 (64 bits), Python 3.11+, domaine Active Directory. Voir CDC section 3.

## Installation (développement)

```bash
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate sous Windows
pip install -r requirements-dev.txt
```

### Lancer les vérifications de qualité et tests :

```bash
ruff check .
mypy systemorion
pytest tests/ -v
```

## État du projet

**Version 0.1.0 complète et validée** :
- Implémentation complète du moteur de sauvegarde en tâche de fond (USN Journal, VSS, impersonation AD, rétention).
- Interface d'administration PySide6 à 2 écrans avec prise en compte dynamique des GPO.
- Modèles ADMX/ADML et paquets de déploiement Inno Setup / WiX MSI.
- 100% des tests unitaires et d'intégration validés sous Linux (headless) et Windows Server.
- Pipeline CI/CD GitHub Actions configuré et opérationnel.
