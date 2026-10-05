# Carte Mentale — System Orion

> **Usage** : Ouvrir avec un rendeur Mermaid (VS Code + plugin, GitHub, mermaid.live)
> **Dernière mise à jour** : 2026-10-05
> **Version projet** : 0.1.0

---

```mermaid
mindmap
  root((System Orion))
    État Global
      Version 0.1.0
      Branche main
      CI/CD opérationnelle
      101 tests passés 100% ✅
    Coeur de Sauvegarde
      Service Windows SYSTEM
        service.py ✅
        Intégration SCM ✅
        Mode standalone ✅
        --install --remove ✅
      Journal USN NTFS
        journal_usn.py ✅
        Lecture incrémentale ✅
        Détection rotation ✅
        Dimensionnement 256 Mo ✅
        Alerte seuil 80% ✅
      VSS ShadowCopy
        vss.py ✅
        Win32_ShadowCopy via WMI ✅
        Suppression garantie ✅
      Cible AD Réseau
        cible_ad.py ✅
        Résolution homeDirectory ✅
        Impersonnification utilisateur ✅
        Mock pour tests Linux ✅
      Transfert & File
        backup.py ✅
        Transfert atomique .part → rename ✅
        Versioning horodaté __YYYYMMDD_HHMM ✅
        Rétention N versions / jours ✅
        Limitation bande passante ✅
        Déduplication SHA-256 fingerprint ✅
        Multi-workers parallèle Robocopy-style ✅
      Persistance SQLite
        state.py ✅
        Mode WAL + synchronous FULL ✅
        Machine à états PENDING COPYING DONE FAILED ✅
        Reset COPYING → PENDING au démarrage ✅
        Purge anciens transferts ✅
        Table backup_history avec content_hash ✅
    Interface Utilisateur
      Panneau Qt6 PySide6
        gui/main_window.py ✅
        2 écrans Dashboard + Dossiers ✅
        Thème sombre Adwaita ✅
        Verrouillage GPO ✅
        EF-01a conforme maquette ✅
      Dialogue Restauration
        gui/restore_dialog.py ✅
        EF-09 restauration ✅
      CLI
        cli.py ✅
        Commande status ✅
    Gestion Configuration
      config.py ✅
        Registre HKLM\SOFTWARE\SystemOrion ✅
        GPO Policies ✅
      models.py ✅
        OrionConfig dataclass ✅
        BackupStats ✅
        Exceptions hiérarchiques ✅
      exclusions.py ✅
        Extensions ✅
        Motifs ✅
        Répertoires exclus ✅
    Journalisation
      logging_agent.py ✅
        Event Log SystemOrion ✅
        Fichiers rotatifs ✅
    Déploiement Packaging
      PyInstaller
        systemorion.spec ✅
        2 binaires Service + Admin ✅
        upx=False (anti-EDR) ✅
      Inno Setup
        installer.iss ✅
        Mode silencieux /VERYSILENT ✅
        Install service --install ✅
      WiX MSI
        systemorion.wxs ✅
        ServiceInstall natif ✅
        Déploiement GPO ✅
      Signature Code
        signtool ✅
        D10 certificat EV ✅
      Orchestrateur
        build.py ✅
        Version dynamique ✅
        Vérification prérequis ✅
        Nettoyage artefacts ✅
    Backend de Stockage
      SMB (production Windows)
        SmbStorageBackend ✅
        Chemins UNC ✅
        EF-03 + D5 ✅
      Drive (tests Linux/macOS)
        DriveStorageBackend ✅
        Dossier synchronisé ✅
        Google Drive / OneDrive ✅
        Test end-to-end ✅
    Tests & Qualité
      Tests unitaires ✅
        test_service ✅
        test_backup ✅
        test_journal_usn ✅
        test_state ✅
        test_config ✅
        test_vss ✅
        test_cible_ad ✅
        test_exclusions ✅
        test_restore ✅
        test_gui ✅
        test_cli ✅
        test_logging ✅
        test_gpo ✅
        test_packaging ✅
        test_advanced_features ✅
      Qualité
        ruff 0 avertissement ✅
        mypy 0 erreur (strict) ✅
        pytest 101/101 passés ✅
      CI/CD
        GitHub Actions ✅
    GPO Active Directory
      ADMX
        SystemOrion.admx ✅
      ADML
        fr-FR/SystemOrion.adml ✅
    Scripts PowerShell
      Deploy-SystemOrion.ps1 ✅
      Uninstall-SystemOrion.ps1 ✅
      Test-OrionEnvironment.ps1 ✅
    Documentation
      CDC v1.3 ✅
      README ✅
      GPO README ✅
      Packaging README ✅
    Hors Périmètre v1.x
      Cloud Azure/AWS ❌
      Chiffrement au repos v2.0 ❌
      Console web centralisée ❌
      Postes hors domaine ❌
    En Attente / Risques
      AIPD DPO obligatoire D9 ⚠️
      Tests EDR antivirus D10 ⚠️
      Avis RSSI chiffrement D11 ⚠️
      Signature code EV ⚠️
```

---

## Légende

| Symbole | Signification |
|---|---|
| ✅ | Implémenté et testé |
| ⚠️ | En attente / Risque identifié |
| ❌ | Hors périmètre v1.x |
| 🚧 | En cours |

---

## Résumé Avancement

| Domaine | Progression |
|---|---|
| Moteur de sauvegarde | 100% |
| Interface utilisateur | 100% |
| Packaging & Déploiement | 100% |
| Tests & Qualité | 100% |
| GPO / AD | 100% |
| Documentation | 100% |
| Validation juridique/RGPD | 0% (externe) |
| Signature de code | 0% (nécessite certificat EV) |
| Tests EDR | 0% (nécessite environnement Windows réel) |

---

## Prochaines Étapes Recommandées

1. **Packaging** : Tests end-to-end sur Windows réel (Inno Setup + WiX)
2. **Signature** : Configurer pipeline avec certificat EV (OV en attendant)
3. **Tests EDR** : Valider non-réaction sur solution représentative
4. **AIPD** : Lancer analyse DPO avant tout déploiement pilote
5. **Versioning spec** : Mettre à jour `.spec` avec version dynamique depuis `__init__.py`
