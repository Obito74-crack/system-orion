# Cahier des Charges — System Orion

| Champ | Valeur |
|---|---|
| Document | Cahier des charges fonctionnel et technique v1.3 |
| Produit | **System Orion** — agent de sauvegarde silencieuse des postes de travail d'entreprise |
| Version | 1.3 — réseau local uniquement (hors cloud) |
| Date | 2026-09-13 |
| Statut | En revue — renommage complet du projet (ex. « Agent de sauvegarde ») en System Orion, identifiants techniques inclus |
| Technologie | Python 3 (Windows) |

---

## 0. Historique des révisions

| Version | Date | Nature du changement |
|---|---|---|
| 1.0 | 2026-09-08 | Version initiale validée en phase de cadrage |
| 1.1 | 2026-09-09 | Gouvernance légale/RGPD renforcée (D9), sécurité applicative et signature de code (D10), chiffrement au repos requalifié en risque actif (D11) ; dimensionnement dynamique USN (EF-04) ; gestion de la tempête de reconnexion (EF-12) ; nouvelle section Stratégie de recette (section 10) ; critères d'acceptation étendus. |
| 1.2 | 2026-09-09 | EF-01a révisé : navigation à deux écrans conforme à la maquette de référence fournie. |
| 1.3 | 2026-09-13 | **Renommage complet du projet en « System Orion »**, y compris les identifiants techniques : nom du service Windows, clé de registre, source Event Log, dossier `ProgramData`, chemin de sauvegarde réseau, nom du package Python. Document consolidé en un seul fichier autoporteur (fin des renvois « voir CDC v1.0 ») pour éviter toute divergence de nommage entre versions. **Aucun impact sur la substance des décisions D1-D11** : renommage uniquement, aucune fonctionnalité ajoutée, retirée ou modifiée. |

### 0.1 Convention de nommage (nouveau v1.3)
| Usage | Valeur |
|---|---|
| Nom produit (affiché, communication, CSE, salariés) | **System Orion** |
| Identifiant technique (sans espace, PascalCase) | `SystemOrion` |
| Nom du service Windows (interne) | `SystemOrion` |
| Nom d'affichage du service (services.msc) | `System Orion` |
| Clé de registre | `HKLM\SOFTWARE\SystemOrion` |
| Source Event Log | `SystemOrion` |
| Dossier `ProgramData` | `C:\ProgramData\SystemOrion\logs` |
| Sous-dossier de sauvegarde réseau | `<homeDirectory>\SystemOrion\<NomPoste>\...` |
| Package Python (minuscules, PEP 8) | `systemorion` |

---

## 1. Contexte et objectif

### 1.1 Constat
Dans les entreprises, les salariés enregistrent leurs documents sur le disque local de leur poste (`C:\Users\...`) au lieu de l'espace de stockage réseau de l'entreprise. Conséquences : perte de données en cas de panne matérielle, vol ou ransomware ; impossibilité de récupérer les données d'un salarié parti ; non-conformité des données métier.

### 1.2 Objectif
Fournir un agent — **System Orion** — installé sur chaque poste qui **sauvegarde automatiquement et silencieusement** les arborescences essentielles de chaque utilisateur vers l'espace de stockage réseau de l'entreprise, **sans aucune action ni accord requis de la part de l'utilisateur** au quotidien, et sans qu'il puisse contourner la sauvegarde.

### 1.3 Principe fondateur
Les décisions validées en phase de cadrage (section 4) constituent la référence. Toute évolution ultérieure ne doit jamais modifier ce qui fonctionne : une fonctionnalité validée ne peut être que complétée, jamais cassée ou retirée sans révision formelle du présent document.

### 1.4 Avertissement de qualification juridique
System Orion constitue, au sens du RGPD et de la doctrine CNIL, un **dispositif de traitement automatisé de données à caractère potentiellement personnel**, même si l'intention fonctionnelle est la protection de données professionnelles. Le fait que l'agent soit silencieux, non désactivable et exécuté en `SYSTEM` renforce cette qualification (absence de maîtrise de l'utilisateur sur ses propres données). **Le déploiement en production est conditionné à la validation du volet 9 (Sécurité et conformité) par un DPO ou juriste habilité — voir D9.** Ce cahier des charges ne constitue pas en lui-même une validation juridique.

---

## 2. Périmètre

### 2.1 Inclus dans la v1.3
- Agent **System Orion** installé sur les postes clients Windows du domaine Active Directory.
- Sauvegarde **ciblée** : uniquement les arborescences sélectionnées (pas de sauvegarde intégrale du disque).
- Décision fichier par fichier : **sauvegarder ou ignorer**, fondée sur la lecture du **journal système NTFS (USN Journal)** des arborescences cibles.
- Copie des fichiers ouverts grâce à un cliché instantané **VSS** du volume source.
- Cible de sauvegarde : **partage réseau SMB local** (`\\SERVEUR\...$`, typiquement le lecteur `Y:` / dossier personnel de l'utilisateur, sous-dossier `SystemOrion`). **Aucun cloud** en v1.x.
- Deux modes d'installation : **manuel** (assistant, type Office) et **silencieux via GPO Active Directory**.
- Restauration : copie de fichiers versionnés depuis l'espace réseau.

### 2.2 Hors périmètre v1.x (roadmap)
- Sauvegarde vers le cloud (Azure, AWS, etc.).
- Chiffrement des sauvegardes au repos — implémentation reportée en v2.0, mais évaluation du risque obligatoire dès v1.x (D11, section 8).
- Console de supervision centralisée web (v1.x = journaux locaux consultables).
- Sauvegarde de postes hors domaine (workgroup) — le mode manuel reste possible mais hors contrat de support v1.x.
- Sauvegarde de volumes autres que le volume système (extension possible).

---

## 3. Environnement cible

| Élément | Spécification |
|---|---|
| Système d'exploitation | Windows 10 / 11 Pro et Entreprise (64 bits), Windows Server 2016+ pour le serveur de fichiers |
| Réseau | Domaine Active Directory, partage SMB (SMB2/SMB3) |
| Système de fichiers source | NTFS (volume système C:) — prérequis au journal USN |
| Droits requis sur le poste | Service Windows `SystemOrion` exécuté en compte `SYSTEM` (local) |
| Déploiement | Assistant manuel ou GPO (stratégie de groupe) |
| Sécurité endpoint | EDR/antivirus d'entreprise à identifier en amont pour tests de compatibilité (D10) |

---

## 4. Décisions validées (référence contractuelle)

### 4.1 Décisions v1.0 (substance inchangée — nommage mis à jour en v1.3)

| # | Décision |
|---|---|
| D1 | Sauvegarde **silencieuse** : aucune interaction avec l'utilisateur, exécution en service Windows `SystemOrion` sous compte `SYSTEM`. L'utilisateur ne peut ni suspendre ni contourner l'agent. |
| D2 | **Ciblage** : sauvegarde uniquement de l'**arborescence essentielle** sélectionnée lors de l'installation/config. Jamais de sauvegarde intégrale. |
| D3 | **Détection** : lecture du **journal système NTFS (USN Journal)** des volumes cibles pour déterminer, fichier par fichier, s'il doit être sauvegardé ou ignoré. |
| D4 | **Fichiers ouverts** : cliché instantané **VSS** du volume source avant copie, garantissant la cohérence sans interrompre l'utilisateur. |
| D5 | **Stockage v1.x** : réseau local uniquement — partage SMB de l'entreprise (`\\SERVEUR\Partage$\<utilisateur>\SystemOrion\<NomPoste>`), attributs AD `homeDirectory` / `homeDrive`. Pas de cloud. |
| D6 | **Authentification réseau** : emprunt d'identité (`impersonation`) du jeton de l'utilisateur connecté. Aucun compte de service aux droits étendus, aucun identifiant stocké. |
| D7 | **Installation** : deux modes — **manuel** (assistant de sélection des arborescences) et **GPO** (installation silencieuse, configuration poussée par stratégie). Les deux modes convergent vers un magasin de configuration unique (`HKLM\SOFTWARE\SystemOrion`) lu par le service. |
| D8 | **Juridique** : déploiement couvert par une charte informatique signée par les employés et par le principe « aucune donnée personnelle sur le poste de travail ». Avis du CSE requis si l'entreprise compte 50 salariés ou plus. |

### 4.2 Décisions v1.1 (complètent D1-D8, substance inchangée)

| # | Décision |
|---|---|
| D9 | **Gouvernance légale préalable au déploiement** : le déploiement en production (pilote inclus) est bloqué tant que (a) une AIPD n'a pas été réalisée ou formellement jugée non requise par le DPO, et (b) chaque salarié concerné n'a pas reçu une information individuelle préalable sur System Orion. |
| D10 | **Sécurité applicative** : le binaire livré (installateur + service `SystemOrion`) est signé avec un certificat de signature de code (EV recommandé) et testé contre au moins une solution EDR/antivirus représentative du parc cible avant tout déploiement au-delà du pilote. |
| D11 | **Chiffrement au repos** : non implémenté en v1.x, mais formellement identifié comme risque de sécurité actif (section 8) devant faire l'objet d'un avis écrit du RSSI avant déploiement à grande échelle. |

---

## 5. Architecture

```
                         ┌────────────────────────────┐
                         │   Active Directory         │
                         │ homeDirectory / homeDrive  │
                         └──────────┬─────────────────┘
                                    │ LDAP/ADSI
┌────────────────┐   USN Journal   │         ┌───────────────────────────┐
│  Poste client  │ ───────────────►│         │ Serveur de fichiers      │
│ System Orion   │                 │         │ \\SRV\Partage$ (SMB)     │
│ (service       │   VSS snapshot  │  SMB    │ Y:\SystemOrion\...       │
│  SYSTEM)       │ ───────────────►│ ──────► │ (versions datées)        │
└────────────────┘                 │         └───────────────────────────┘
        ▲                          │
        └── Impersonnification du jeton de l'utilisateur connecté
            (WTSQueryUserToken → ImpersonateLoggedOnUser)
```

### 5.1 Composants logiciels
- **Service Windows « SystemOrion »** (nom d'affichage « System Orion ») : processus principal (pywin32), exécuté en `SYSTEM`, sans interface utilisateur.
- **Installateur** : empaquetage de l'agent + runtime Python (PyInstaller), installé via assistant (mode manuel) ou silencieusement (mode GPO), **signé numériquement (D10)**.
- **Module de configuration** : magasin unique (clés de registre `HKLM\SOFTWARE\SystemOrion`), écrit par l'assistant en mode manuel ou par GPO (modèle ADMX) en mode silencieux.
- **Base locale d'état** (SQLite) : dernier USN traité par volume, identifiant de journal, files d'attente, historique des sauvegardes.

---

## 6. Exigences fonctionnelles

### EF-01 — Installation en mode manuel
- L'administrateur lance l'installateur System Orion sur le poste.
- Assistant graphique permettant de :
  - tester la connectivité au domaine et au partage cible ;
  - **sélectionner les arborescences à sauvegarder** (dossiers connus : Documents, Bureau, Images, Favoris ; chemins personnalisés) ;
  - définir les exclusions (extensions, motifs, chemins — ex. `*.tmp`, `node_modules`, `AppData\Local\Temp`) ;
  - définir la planification (continu par journal / périodicité) ;
  - saisir éventuellement le chemin UNC du partage si différent de l'attribut AD.
- Écrit la configuration dans le magasin unique (`HKLM\SOFTWARE\SystemOrion`) puis installe et démarre le service `SystemOrion`.

### EF-01a — Panneau de configuration graphique (référence : maquette fournie)
Un panneau de configuration graphique (PySide6/Qt6) reprend le style et la structure de navigation de la maquette prototype fournie (esprit GNOME/Adwaita sombre, transposé en Qt pour Windows), en **navigation à deux écrans**. Il s'adresse à l'**administrateur**, s'exécute **élevé** (droits admin) en session utilisateur, et est lancé à la fin de l'installation manuelle ou depuis le menu Démarrer (« System Orion »). **Le service ne l'affiche jamais** (isolation Session 0).

**Écran 1 — Fenêtre principale**
- Barre supérieure : « Annuler » à gauche, titre « System Orion » au centre, « Sauvegarder » à droite.
- Section **Stockage** :
  - **Emplacement** : liste déroulante, seul choix disponible en v1.x = « Serveur réseau ».
  - **Adresse du serveur** : pré-remplie automatiquement depuis Active Directory (`homeDirectory`/`homeDrive`, EF-03), éditable via icône crayon ; icône d'information (ⓘ) donnant le détail de la résolution AD.
  - **Dossier** : sous-dossier cible pré-rempli (`<homeDirectory>\SystemOrion\<NomPoste>`), éditable via icône crayon.
- Section **Dossiers à sauvegarder** : aperçu résumé de la sélection courante (ex. « Dossier personnel (NomPoste) » présélectionné) avec accès à l'écran 2 pour la gestion complète.

**Écran 2 — Sous-écran « Dossiers »**
- Section **Dossiers à sauvegarder** : dossiers connus de l'utilisateur (Documents, Bureau, Images, Favoris — « Dossier personnel » présélectionné) + chemins personnalisés ; ajout via « Ajouter un dossier sauvegardé… », suppression par icône corbeille.
- Section **Dossiers à ignorer** : présélection = Corbeille (`$RECYCLE.BIN`) et `~/Téléchargements` ; ajout de chemins personnalisés et de **motifs** (`*.tmp`, `node_modules`) via « Ajouter un dossier ignoré… » ; icône d'information (ⓘ) sur la syntaxe des motifs ; suppression par icône corbeille.
- Bouton **« Réinitialiser tous les dossiers… »** : réinitialise aux valeurs par défaut, avec confirmation.
- Retour à l'écran 1 : les modifications de l'écran 2 ne sont écrites qu'au clic sur « Sauvegarder » de l'écran 1 (le bouton « Annuler » global doit pouvoir tout abandonner).

**Comportements transverses**
- **Verrouillage GPO** : si `ManagedByGpo` est actif, tous les champs passent en lecture seule avec mention « Géré par votre organisation » (D7).
- **Validation** : « Sauvegarder » écrit `HKLM\SOFTWARE\SystemOrion` et notifie le service ; « Annuler » abandonne sans écrire. Test de connectivité proposé avant écriture.
- **Langue** : interface 100 % française, chaînes externalisées pour traduction future.

### EF-02 — Installation en mode GPO (silencieuse)
- Package System Orion déployé par GPO (`Configuration ordinateur → Paramètres du logiciel → Installation de logiciel`) : installation au démarrage, sans aucune fenêtre.
- En l'absence d'interface, la **configuration provient de la GPO** (modèle ADMX `SystemOrion.admx` ou clés de registre déployées) : arborescences, exclusions, planification, partage cible.
- Comportement du service strictement identique au mode manuel une fois configuré (D7).

### EF-03 — Découverte de la cible réseau par utilisateur
- Au démarrage d'une session de sauvegarde, l'agent résout l'espace cible de l'utilisateur connecté en interrogeant Active Directory (attributs `homeDirectory` / `homeDrive` via ADSI ou LDAP).
- Chemin de sauvegarde : `<homeDirectory>\SystemOrion\<NomPoste>\<Arborescence>\...`.
- Si l'attribut est absent : journaliser l'anomalie, passer l'utilisateur (aucune écriture dans un emplacement par défaut non autorisé).

### EF-04 — Détection des changements (USN Journal)
- L'agent interroge le journal USN du volume système via `DeviceIoControl` / `FSCTL_QUERY_USN_JOURNAL` puis `FSCTL_READ_USN_JOURNAL` (lecture sélective par raison de modification et filtrage sur les arborescences cibles).
- Persistance du dernier USN traité par volume : au redémarrage du service, reprise exacte où l'on s'était arrêté.
- **Détection de rotation du journal** : si l'identifiant du journal a changé ou si le dernier USN traité est antérieur au premier USN valide, l'agent déclenche une **sauvegarde complète de référence** des arborescences cibles avant de reprendre le mode incrémental.
- **Dimensionnement initial** : l'agent augmente la taille du journal au premier démarrage (`FSCTL_CREATE_USN_JOURNAL`, valeur par défaut 256 Mo).
- **Dimensionnement dynamique** : l'agent mesure le débit d'écriture d'enregistrements USN sur les 30 premiers jours et journalise une alerte si la taille configurée couvre moins de 72 h d'activité observée au rythme le plus soutenu constaté. Ajustable via la configuration sans réinstallation.
- **Alerte proactive avant rotation** : compteur d'utilisation du journal journalisé à chaque cycle ; seuil configurable (défaut 80 %) déclenchant une alerte Event Log `SystemOrion` distincte de la bascule en sauvegarde complète.

### EF-05 — Décision « sauvegarder / ignorer »
Pour chaque fichier signalé par le journal :
- **Ignorer** si : hors arborescences cibles ; extension/exclusion configurée ; fichier temporaire ou verrouillage système ; taille nulle non pertinente ; chemin contenant des répertoires exclus.
- **Ignorer** si le fichier n'existe plus à la copie (suppression entre détection et traitement) — consigner simplement l'événement.
- **Sauvegarder** sinon.

### EF-06 — Sauvegarde cohérente des fichiers ouverts (VSS)
- Avant chaque vague de copie, création d'un cliché instantané du volume C: par la classe WMI `Win32_ShadowCopy` (contexte `ClientAccessible`).
- Copie effectuée depuis le chemin du cliché (`\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopyN\...`), puis suppression du cliché.
- En cas d'échec VSS : repli sur copie directe avec retry sur violation de partage (3 tentatives espacées) ; échec final consigné pour traitement au prochain cycle.
- Un seul cliché à la fois, durée de vie bornée (suppression garantie même en cas d'erreur).

### EF-07 — Copie vers le partage réseau
- Copie incrémentale : seuls les fichiers créés/modifiés/renommés sont transférés.
- Préservation des métadonnées utiles (horodatage de modification) permettant les comparaisons futures.
- **Aucune suppression** côté sauvegarde lors d'une suppression source en v1.x (les versions restent consultables) — sauf nettoyage par règle de rétention (EF-08).
- Reprise sur incident réseau : files d'attente persistantes (SQLite), reprise automatique, limitation de bande passante paramétrable.
- Le transfert s'effectue sous l'identité de l'utilisateur connecté (EF-03, D6) : les ACL du dossier personnel AD s'appliquent telles quelles.

### EF-08 — Versioning et rétention
- Une modification n'écrase jamais la version précédente : la nouvelle version est stockée avec son horodatage (ex. `rapport.docx` → `rapport__20260908_1430.docx` ou sous-répertoires datés).
- Règle de rétention configurable (ex. conserver les N dernières versions par fichier et/ou durée maximale), appliquée par l'agent lors du nettoyage périodique.

### EF-09 — Restauration
- Restauration = copie des fichiers/versions souhaités depuis `Y:\SystemOrion\...` vers le poste, par l'administrateur ou l'utilisateur autorisé, en exploitation normale (explorateur Windows). Aucun module de restauration dédié en v1.x.
- L'arborescence de sauvegarde étant lisible et horodatée, la restauration ne dépend pas de l'agent.

### EF-10 — Journalisation et supervision locale
- Journal Windows (Event Log) dédié « SystemOrion » : démarrages/arrêts, cycles de sauvegarde, fichiers sauvegardés/ignorés (compteurs), erreurs, espace cible insuffisant, échecs VSS, rotations de journal détectées.
- Fichier de log local rotatif (`C:\ProgramData\SystemOrion\logs`).
- Journalisation minimale des contenus : aucun contenu de fichier dans les logs (conformité D8).

### EF-11 — Mise à jour et désinstallation
- Mise à jour : réinstallation du package System Orion par le même canal (manuel ou GPO) ; le magasin de configuration (`HKLM\SOFTWARE\SystemOrion`) et la base d'état sont conservés.
- Désinstallation : suppression du service `SystemOrion`, des binaires et de la configuration ; les sauvegardes sur le serveur ne sont **jamais** effacées par la désinstallation.

### EF-12 — Résilience aux déconnexions réseau (postes mobiles, Wi-Fi, VPN)
Principe directeur : **découplage total de la détection (locale) et du transfert (réseau)**. La détection ne dépend jamais de la disponibilité réseau ; le transfert reprend toujours proprement.

- **File d'attente persistante** (SQLite) : tout fichier détecté par le journal USN mais non encore copié y est conservé ; il survit à l'arrêt du service, aux déconnexions et aux redémarrages du poste.
- **Machine à états par fichier** : `PENDING → COPYING → DONE`. Au redémarrage, tout fichier en état `COPYING` repasse en `PENDING` et est recopié intégralement.
- **Transfert atomique** : copie vers un fichier temporaire `<nom>.part` sur le partage, puis `rename` final (atomique sur SMB).
- **Surveillance réseau avec backoff exponentiel** : 10 s, 30 s, 1 min, 5 min… la détection locale continue pendant l'indisponibilité.
- **Coupures brutes du poste** : base d'état SQLite (WAL + `synchronous=FULL`) durable et auto-réparatrice.
- **Microcoupures** : bénéfice gratuit des *durable handles* SMB3 natifs Windows ; la machine à états SQLite reste le mécanisme principal.
- **Gestion de la tempête de reconnexion** : gigue de reprise (0-15 min, configurable) + limitation de bande passante conservatrice à la reconnexion, relâchée progressivement, paramétrable par GPO.

---

## 7. Exigences techniques

### ET-01 — Stack Python (décisions finales)
| Besoin | Brique retenue | Justification |
|---|---|---|
| Langage | Python 3.11+ (64 bits) | Écosystème Windows mature |
| Service Windows, USN Journal, impersonnification, registre, Event Log | `pywin32` (`win32file`, `win32ioctlcon`, `win32ts.WTSQueryUserToken`, `win32security.ImpersonateLoggedOnUser`, `win32serviceutil`) | Une seule dépendance pour les 4 briques critiques |
| VSS | `Win32_ShadowCopy` (WMI) via sous-processus PowerShell/CIM | `vssadmin create` retiré de Windows 11 ; `wmic` déprécié |
| Requête AD | ADSI via `win32com` (`WinNT://domaine/utilisateur`) | Zéro dépendance supplémentaire |
| Base d'état | `sqlite3` (stdlib) — mode WAL + `synchronous=FULL` | Durabilité après coupure de courant |
| Empaquetage | PyInstaller (one-dir) + installateur Inno Setup (silencieux `/VERYSILENT`), enveloppe MSI si GPO « Installation de logiciel » natif ; **binaire et installateur signés (D10, ET-04)** | MSI requis pour l'attribution GPO |
| Configuration | Registre `HKLM\SOFTWARE\SystemOrion` + modèle ADMX `SystemOrion.admx` | Magasin unique (D7) |

### ET-02 — Structure du code
```
systemorion/
├── service.py          # Point d'entrée du service Windows « SystemOrion »
├── config.py           # Lecture/écriture de HKLM\SOFTWARE\SystemOrion
├── journal_usn.py      # Requête USN, filtrage, reprise sur USN, détection rotation
├── vss.py              # Création/suppression de clichés Win32_ShadowCopy
├── cible_ad.py         # Résolution homeDirectory/homeDrive, impersonnification
├── backup.py           # File de copie, versioning, reprise réseau, rétention
├── exclusions.py       # Évaluation des règles d'exclusion
├── logging_agent.py    # Event Log « SystemOrion » + fichiers rotatifs
└── state.py            # Persistance SQLite (USN, file d'attente, machine à états, historique)
```

### ET-03 — Cycle de fonctionnement
1. Démarrage du service `SystemOrion` : chargement configuration → connexion base d'état → dimensionnement USN → boucle principale.
2. Boucle principale : lecture des nouveaux enregistrements USN → filtrage (EF-05) → mise en file → création VSS → copie sous impersonnification → suppression VSS → mise à jour USN traité.
3. Sur verrouillage long : report à la prochaine itération ; sur indisponibilité réseau : files persistantes.
4. Tâches planifiées internes : rétention/nettoyage, rotation des logs, contrôle d'espace cible.

### ET-04 — Signature de code et compatibilité EDR
| Besoin | Exigence |
|---|---|
| Signature | Installateur (MSI/Inno Setup) et exécutables PyInstaller de System Orion signés avec un certificat de signature de code valide (EV recommandé). |
| Compatibilité EDR | Tests de non-régression contre au moins une solution EDR/antivirus représentative avant tout déploiement au-delà du pilote (D10). |
| Justification | Profil comportemental (service SYSTEM, `SeTcbPrivilege`, `ImpersonateLoggedOnUser`, `FSCTL_READ_USN_JOURNAL`) recoupant des heuristiques de détection ransomware/infostealer. |

---

## 8. Contraintes et risques techniques identifiés

| Risque | Mitigation |
|---|---|
| Rotation du journal USN (taille par défaut ~32 Mo sur C:) | Dimensionnement dynamique et alerte proactive (EF-04) + détection d'identifiant de journal changé → sauvegarde complète de référence |
| `FSCTL_READ_USN_JOURNAL` strict sur Windows 10/11 | Structures packées via `struct` conformes aux en-têtes Microsoft ; tests sur cible 10/11 dès le prototype |
| `vssadmin create` indisponible sur Windows 11 | Utilisation systématique de `Win32_ShadowCopy` (WMI) |
| `wmic` déprécié/retiré des Windows récents | Appels CIM via PowerShell ou COM |
| Isolation de session (Session 0) | Toujours utiliser le chemin UNC (`homeDirectory`), jamais la lettre de lecteur |
| `WTSQueryUserToken` exige `SeTcbPrivilege` | Architecture conforme (D1) |
| Cliché VSS unique par volume | Un seul cliché à la fois, verrou interne, suppression garantie |
| Espace cible insuffisant | Surveillance et alerte dans le journal `SystemOrion` |
| Faux positifs EDR/antivirus sur le comportement du service | Signature de code + tests de compatibilité préalables (D10, ET-04) |
| Données stockées en clair sur le partage réseau | Risque actif nécessitant avis écrit du RSSI avant déploiement à grande échelle (D11) |
| Tempête de reconnexion après panne réseau généralisée | Gigue de reprise + limitation de bande passante progressive (EF-12) |
| Impossibilité de garantir l'absence de données personnelles dans les arborescences | Politique organisationnelle (D8), pas une garantie technique — traité au volet légal (D9, section 9) |

---

## 9. Sécurité et conformité

### 9.1 Principes techniques
- **Principe du moindre privilège** : le service `SystemOrion` est local (`SYSTEM`) ; l'accès réseau s'effectue exclusivement sous l'identité de l'utilisateur connecté (D6).
- **Contenus jamais journalisés** : métadonnées uniquement (chemins, compteurs, codes erreur).
- **Intégrité des sauvegardes** : horodatage à la copie ; versions non écrasables par l'utilisateur (ACL du dossier personnel).

### 9.2 Cadre juridique et RGPD
- **Qualification** : System Orion constitue un traitement automatisé pouvant porter sur des données à caractère personnel (voir 1.4).
- **AIPD** : à réaliser ou à faire formellement écarter par le DPO avant tout déploiement, y compris pilote (D9).
- **Information individuelle des salariés** : information spécifique sur System Orion (finalité, données concernées, durée de conservation, absence de contournement possible, modalités d'exercice des droits RGPD).
- **Avis du CSE** : requis si l'entreprise compte 50 salariés ou plus (D8).
- **Proportionnalité** : ciblage strict des arborescences professionnelles (D2), à documenter dans l'AIPD.
- **Durée de conservation** : politique de rétention (EF-08) à justifier explicitement (durée de conservation au sens RGPD).
- **Droits des personnes** : procédure permettant de répondre à une demande d'accès/suppression, notamment après départ d'un salarié.

### 9.3 Sécurité applicative
- Signature de code de l'installateur et des exécutables System Orion (D10, ET-04).
- Tests de compatibilité EDR/antivirus avant déploiement au-delà du pilote.
- Chiffrement au repos identifié comme risque actif nécessitant avis RSSI écrit avant déploiement à grande échelle (D11).

---

## 10. Stratégie de recette

### 10.1 Environnement de test
- Environnement isolé reproduisant le domaine AD, un partage SMB de test, au moins un poste Windows 10 et un poste Windows 11 à jour.
- Jeu de données de test : fichiers volumineux, fichiers verrouillés en continu, volume d'écriture soutenu pour valider le dimensionnement USN.

### 10.2 Déploiement pilote
- Pilote sur un groupe restreint (10-20 postes), profils d'usage variés, durée couvrant un cycle de rotation USN naturel.
- Le pilote est la première étape autorisée après validation D9 — pas avant.
- Procédure de rollback documentée (désinstallation + conservation des sauvegardes, EF-11).

### 10.3 Vérification des critères d'acceptation
Chaque critère de la section 11 est vérifié par un scénario de test explicite, rejoué avant chaque montée de version majeure.

---

## 11. Critères d'acceptation

1. Installation manuelle complète en moins de 10 minutes, sélection d'arborescences incluse.
2. Installation GPO silencieuse au démarrage, sans fenêtre ni interaction.
3. Création/modification d'un fichier dans une arborescence cible → sauvegardé sur le partage avant le délai planifié, utilisateur ouvert ou non.
4. Fichier hors arborescence ou exclu → jamais copié, présence constatable dans les journaux de décision.
5. Redémarrage du poste/service → reprise exacte au dernier USN traité, sans doublon inutile.
6. Suppression d'un fichier source → versions précédentes toujours présentes sur le partage.
7. Journal de décision consultable (Event Log `SystemOrion` + fichier local) avec compteurs sauvegardés/ignorés/erreurs.
8. Désinstallation propre (service `SystemOrion` retiré, aucune donnée de sauvegarde effacée).
9. Installateur et service signés numériquement ; aucune alerte bloquante sur l'EDR/antivirus testé (D10).
10. Simulation d'activité disque soutenue → alerte proactive d'utilisation du journal USN déclenchée avant rotation effective (EF-04).
11. Simulation d'une coupure réseau généralisée sur le parc pilote → reprise étalée dans le temps, pas de saturation constatée du lien serveur (EF-12).
12. AIPD réalisée ou formellement écartée par le DPO, et information individuelle des salariés du pilote effectuée, avant démarrage du pilote (D9).

---

## 12. Roadmap post-v1.3 (non contractuel)

- v1.x (extension technique) : extensions multi-volumes, exclusions par modèle avancé, console de supervision.
- v2.0 : cible cloud chiffrée, chiffrement au repos en v1-réseau si l'avis RSSI (D11) l'impose avant, restauration assistée, politiques par groupes AD, ordonnancement centralisé de la reprise réseau par site.

---

*Document de référence — toute modification des décisions D1 à D11 exige une révision formelle validée par le porteur du projet. Le déploiement en production, y compris le pilote, est subordonné à la validation du volet 9 par un DPO ou juriste habilité (D9).*
