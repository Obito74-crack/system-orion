# Packaging et Déploiement — System Orion

Ce dossier contient l'ensemble des scripts et fichiers de configuration pour générer les paquets de distribution de **System Orion** selon les exigences **ET-01, ET-04, EF-01, EF-02 et EF-11** du CDC v1.3.

---

## 1. Composants produits

1. **Distribution binaire autonome (PyInstaller one-dir)** :
   - `SystemOrionService.exe` : Service Windows exécuté en compte `SYSTEM`.
   - `SystemOrionAdmin.exe` : Panneau de configuration graphique administrateur Qt6 / PySide6.
2. **Installateur autonome (.exe — Inno Setup)** :
   - Assistant interactif (mode manuel EF-01 / EF-01a).
   - Mode silencieux automatisé : `/VERYSILENT /NORESTART`.
3. **Paquet MSI (.msi — WiX Toolset)** :
   - Déploiement silencieux par GPO Active Directory (`Configuration ordinateur -> Installation de logiciel`).

---

## 2. Prérequis de compilation (sous Windows)

- Python 3.11+ 64 bits avec dépendances installées :
  ```cmd
  pip install pyinstaller PySide6 pywin32
  ```
- **Inno Setup 6+** (installé dans `C:\Program Files (x86)\Inno Setup 6\`)
- **WiX Toolset v3.11+** (dans le PATH ou via extension Visual Studio)
- Certificat de signature de code (EV recommandé, CDC D10 / ET-04)

---

## 3. Lancer la chaîne de packaging

Exécuter le script orchestrateur `build.py` :

```cmd
python packaging\build.py
```

Options disponibles :
```cmd
python packaging\build.py --cert-file C:\certs\systemorion.pfx --cert-pass "SecretPass"
python packaging\build.py --skip-msi
```

---

## 4. Déploiement silencieux GPO (CDC EF-02)

### Ligne de commande Inno Setup :
```cmd
SystemOrion_Setup_0.1.0.exe /VERYSILENT /NORESTART /SUPPRESSMSGBOXES
```

### Ligne de commande MSI (msiexec) :
```cmd
msiexec /i SystemOrion_0.1.0.msi /qn /norestart
```

---

## 5. Désinstallation (CDC EF-11)

La désinstallation arrête et supprime le service Windows `SystemOrion`, supprime les binaires et la base locale `state.db`.

> **Important (EF-11)** : Les données et versions déjà transférées sur le partage réseau SMB (`\\serveur\partage$\...`) ne sont **JAMAIS** supprimées lors de la désinstallation.
