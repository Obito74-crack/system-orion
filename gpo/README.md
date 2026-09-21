# Modèles d'Administration Active Directory (GPO) — System Orion

Ce dossier contient les définitions de stratégies de groupe (ADMX / ADML) pour le déploiement et la gestion centralisée de **System Orion** (CDC EF-02).

## Fichiers fournis

- `SystemOrion.admx` : Structure et métadonnées des règles (espace de noms `SOFTWARE\Policies\SystemOrion`).
- `fr-FR/SystemOrion.adml` : Chaînes textuelles et interface d'édition en français.

## Déploiement dans le domaine

### Méthode 1 : Magasin central (Central Store - Recommandé)
1. Copier `SystemOrion.admx` vers :
   ```
   \\<votre-domaine.local>\SYSVOL\<votre-domaine.local>\Policies\PolicyDefinitions\
   ```
2. Copier `fr-FR/SystemOrion.adml` vers :
   ```
   \\<votre-domaine.local>\SYSVOL\<votre-domaine.local>\Policies\PolicyDefinitions\fr-FR\
   ```

### Méthode 2 : Poste local d'administration
1. Copier `SystemOrion.admx` dans `C:\Windows\PolicyDefinitions\`
2. Copier `fr-FR/SystemOrion.adml` dans `C:\Windows\PolicyDefinitions\fr-FR\`

## Utilisation
Ouvrir la console `gpmc.msc` (Gestion des stratégies de groupe) :
- Naviguer vers : `Configuration ordinateur` → `Stratégies` → `Modèles d'administration` → `System Orion`.
- Les catégories disponibles correspondent aux exigences CDC :
  - **Stockage et Partage SMB**
  - **Arborescences à sauvegarder**
  - **Règles d'exclusion**
  - **Versioning et Rétention**
  - **Journal USN NTFS**
  - **Réseau et Résilience**

L'activation de la politique principale **« Verrouiller la configuration par stratégie d'organisation (ManagedByGpo) »** applique le verrouillage strict de l'interface graphique administrateur (`EF-01a`).
