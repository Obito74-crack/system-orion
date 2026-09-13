# Cahier des Charges — Agent de Sauvegarde Automatique des Postes de Travail

| Champ | Valeur |
|---|---|
| Document | Cahier des charges fonctionnel et technique v1.1 |
| Produit | Agent de sauvegarde silencieuse des postes de travail d'entreprise |
| Version | 1.2 — réseau local uniquement (hors cloud) |
| Date | 2026-09-09 |
| Statut | En revue — intègre les amendements légaux, sécurité, recette (v1.1) et la maquette validée du panneau de configuration (v1.2) |
| Technologie | Python 3 (Windows) |

---

## 0. Historique des révisions

| Version | Date | Nature du changement |
|---|---|---|
| 1.0 | 2026-09-08 | Version initiale validée en phase de cadrage |
| 1.1 | 2026-09-09 | Ajout : gouvernance légale/RGPD renforcée (D9), sécurité applicative et signature de code (D10), chiffrement au repos requalifié en risque actif (D11) ; dimensionnement dynamique USN (EF-04 modifié) ; gestion de la tempête de reconnexion (EF-12 complété) ; nouvelle section Stratégie de recette (section 10) ; critères d'acceptation étendus. **Aucune décision D1-D8 n'est modifiée ou retirée**, conformément au principe fondateur (1.3). |
| 1.2 | 2026-09-09 | **EF-01a révisé** suite à la maquette de référence fournie : le panneau de configuration passe d'un écran unique à trois sections à une **navigation à deux écrans** (écran principal Stockage + résumé, sous-écran dédié "Dossiers" pour la gestion fine sauvegardés/ignorés), conformément à la maquette validée. Aucun impact sur D1-D11 : modification d'un détail d'implémentation d'une exigence fonctionnelle, pas d'une décision verrouillée. |

---

## 1. Contexte et objectif

### 1.1 Constat
Dans les entreprises, les salariés enregistrent leurs documents sur le disque local de leur poste (`C:\Users\...`) au lieu de l'espace de stockage réseau de l'entreprise. Conséquences : perte de données en cas de panne matérielle, vol ou ransomware ; impossibilité de récupérer les données d'un salarié parti ; non-conformité des données métier.

### 1.2 Objectif
Fournir un agent installé sur chaque poste qui **sauvegarde automatiquement et silencieusement** les arborescences essentielles de chaque utilisateur vers l'espace de stockage réseau de l'entreprise, **sans aucune action ni accord requis de la part de l'utilisateur** au quotidien, et sans qu'il puisse contourner la sauvegarde.

### 1.3 Principe fondateur
Les décisions validées en phase de cadrage (section 4) constituent la référence. Toute évolution ultérieure ne doit jamais modifier ce qui fonctionne : une fonctionnalité validée ne peut être que complétée, jamais cassée ou retirée sans révision formelle du présent document.

### 1.4 Avertissement de qualification juridique (nouveau en v1.1)
Ce produit constitue, au sens du RGPD et de la doctrine CNIL, un **dispositif de traitement automatisé de données à caractère potentiellement personnel**, même si l'intention fonctionnelle est la protection de données professionnelles. Le fait que l'agent soit silencieux, non désactivable et exécuté en `SYSTEM` renforce cette qualification (absence de maîtrise de l'utilisateur sur ses propres données). **Le déploiement en production est conditionné à la validation du volet 9 (Sécurité et conformité) par un DPO ou juriste habilité — voir D9.** Ce cahier des charges ne constitue pas en lui-même une validation juridique.

---

## 2. Périmètre

### 2.1 Inclus dans la v1.0/v1.1
- Agent installé sur les postes clients Windows du domaine Active Directory.
- Sauvegarde **ciblée** : uniquement les arborescences sélectionnées (pas de sauvegarde intégrale du disque).
- Décision fichier par fichier : **sauvegarder ou ignorer**, fondée sur la lecture du **journal système NTFS (USN Journal)** des arborescences cibles.
- Copie des fichiers ouverts grâce à un cliché instantané **VSS** du volume source.
- Cible de sauvegarde : **partage réseau SMB local** (`\\SERVEUR\...$`, typiquement le lecteur `Y:` / dossier personnel de l'utilisateur). **Aucun cloud** en v1.0.
- Deux modes d'installation : **manuel** (assistant, type Office) et **silencieux via GPO Active Directory**.
- Restauration : copie de fichiers versionnés depuis l'espace réseau.

### 2.2 Hors périmètre v1.0 (roadmap)
- Sauvegarde vers le cloud (Azure, AWS, etc.).
- Chiffrement des sauvegardes au repos — **implémentation reportée en v2.0, mais évaluation du risque obligatoire dès v1.0 (voir D11, section 8).**
- Console de supervision centralisée web (v1.0 = journaux locaux consultables).
- Sauvegarde de postes hors domaine (workgroup) — le mode manuel reste possible mais hors contrat de support v1.0.
- Sauvegarde de volumes autres que le volume système (extension possible).

---

## 3. Environnement cible

| Élément | Spécification |
|---|---|
| Système d'exploitation | Windows 10 / 11 Pro et Entreprise (64 bits), Windows Server 2016+ pour le serveur de fichiers |
| Réseau | Domaine Active Directory, partage SMB (SMB2/SMB3) |
| Système de fichiers source | NTFS (volume système C:) — prérequis au journal USN |
| Droits requis sur le poste | Service exécuté en compte `SYSTEM` (local) |
| Déploiement | Assistant manuel ou GPO (stratégie de groupe) |
| Sécurité endpoint (nouveau v1.1) | EDR/antivirus d'entreprise à identifier en amont pour tests de compatibilité (voir D10) |

---

## 4. Décisions validées (référence contractuelle)

### 4.1 Décisions v1.0 (inchangées)

| # | Décision |
|---|---|
| D1 | Sauvegarde **silencieuse** : aucune interaction avec l'utilisateur, exécution en service Windows `SYSTEM`. L'utilisateur ne peut ni suspendre ni contourner l'agent. |
| D2 | **Ciblage** : sauvegarde uniquement de l'**arborescence essentielle** sélectionnée lors de l'installation/config. Jamais de sauvegarde intégrale. |
| D3 | **Détection** : lecture du **journal système NTFS (USN Journal)** des volumes cibles pour déterminer, fichier par fichier, s'il doit être sauvegardé ou ignoré. |
| D4 | **Fichiers ouverts** : cliché instantané **VSS** du volume source avant copie, garantissant la cohérence sans interrompre l'utilisateur. |
| D5 | **Stockage v1.0** : réseau local uniquement — partage SMB de l'entreprise (`\\SERVEUR\Partage$\<utilisateur>`), attributs AD `homeDirectory` / `homeDrive`. Pas de cloud. |
| D6 | **Authentification réseau** : emprunt d'identité (`impersonation`) du jeton de l'utilisateur connecté. Aucun compte de service aux droits étendus, aucune identifiant stocké. |
| D7 | **Installation** : deux modes — **manuel** (assistant de sélection des arborescences) et **GPO** (installation silencieuse, configuration poussée par stratégie). Les deux modes convergent vers un magasin de configuration unique lu par le service. |
| D8 | **Juridique** : déploiement couvert par une charte informatique signée par les employés et par le principe « aucune donnée personnelle sur le poste de travail ». Avis du CSE requis si l'entreprise compte 50 salariés ou plus. |

### 4.2 Décisions nouvelles v1.1 (complètent, ne modifient pas D1-D8)

| # | Décision |
|---|---|
| **D9** | **Gouvernance légale préalable au déploiement** : le déploiement en production (pilote inclus) est bloqué tant que (a) une Analyse d'Impact relative à la Protection des Données (AIPD) n'a pas été réalisée ou formellement jugée non requise par le DPO, et (b) chaque salarié concerné n'a pas reçu une information individuelle préalable (pas seulement une charte signée à l'embauche). Ceci complète D8 sans le remplacer. |
| **D10** | **Sécurité applicative** : le binaire livré (installateur + service) est signé avec un certificat de signature de code (EV recommandé) et testé contre au moins une solution EDR/antivirus représentative du parc cible avant tout déploiement au-delà du pilote, en raison du profil comportemental à haut risque de faux positif (service SYSTEM, `SeTcbPrivilege`, lecture bas niveau du journal USN). |
| **D11** | **Chiffrement au repos** : non implémenté en v1.0 par décision de périmètre (2.2), mais formellement identifié comme risque de sécurité actif (section 8) devant faire l'objet d'un avis écrit du RSSI avant déploiement à grande échelle, et non simplement laissé en roadmap non contractuelle. |

---

## 5. Architecture

```
                         ┌────────────────────────────┐
                         │   Active Directory         │
                         │ homeDirectory / homeDrive  │
                         └──────────┬─────────────────┘
                                    │ LDAP/ADSI
┌────────────────┐   USN Journal   │         ┌──────────────────────┐
│  Poste client  │ ───────────────►│         │ Serveur de fichiers  │
│ Agent Python   │                 │         │ \\SRV\Partage$ (SMB) │
│ (service       │   VSS snapshot  │  SMB    │ Y:\Sauvegardes\...   │
│  SYSTEM)       │ ───────────────►│ ──────► │ (versions datées)    │
└────────────────┘                 │         └──────────────────────┘
        ▲                          │
        └── Impersonnification du jeton de l'utilisateur connecté
            (WTSQueryUserToken → ImpersonateLoggedOnUser)
```

### 5.1 Composants logiciels
- **Service Windows « AgentSauvegarde »** : processus principal (pywin32), exécuté en `SYSTEM`, sans interface utilisateur.
- **Installateur** : empaquetage de l'agent + runtime Python (PyInstaller), installé via assistant (mode manuel) ou silencieusement (mode GPO), **signé numériquement (D10)**.
- **Module de configuration** : magasin unique (clés de registre `HKLM\SOFTWARE\AgentSauvegarde`), écrit par l'assistant en mode manuel ou par GPO (modèle ADMX) en mode silencieux.
- **Base locale d'état** (SQLite) : dernier USN traité par volume, identifiant de journal, files d'attente, historique des sauvegardes.

---

## 6. Exigences fonctionnelles

*(EF-01, EF-02, EF-03, EF-05, EF-06, EF-08, EF-09, EF-10, EF-11 inchangées par rapport à la v1.0 — non reproduites ici pour éviter toute divergence de version ; voir CDC v1.0 section 6 pour le texte de référence intégral. EF-01a est révisé ci-dessous en v1.2.)*

### EF-01a — Panneau de configuration graphique (référence : maquette fournie) — **révisé en v1.2**
Un panneau de configuration graphique (PySide6/Qt6) reprend le style et la structure de navigation de la maquette prototype fournie (esprit GNOME/Adwaita sombre, transposé en Qt pour Windows). Contrairement à la v1.0 (« écran unique en trois sections »), la maquette de référence impose une **navigation à deux écrans**. Il s'adresse à l'**administrateur**, s'exécute **élevé** (droits admin) en session utilisateur, et est lancé à la fin de l'installation manuelle ou depuis le menu Démarrer. **Le service ne l'affiche jamais** (isolation Session 0 — une interface créée par un service n'apparaît sur aucun bureau utilisateur).

**Écran 1 — Fenêtre principale (« New Backup »/paramètres de sauvegarde)**
- Barre supérieure : « Annuler » (abandon sans écriture) à gauche, titre au centre, « Sauvegarder » (validation, mise en évidence visuelle) à droite.
- Section **Stockage** :
  - **Emplacement** : liste déroulante, seul choix disponible en v1.0 = « Serveur réseau ».
  - **Adresse du serveur** : pré-remplie automatiquement depuis Active Directory (`homeDirectory`/`homeDrive`, EF-03), éditable via icône crayon ; icône d'information (ⓘ) donnant le détail de la résolution AD.
  - **Dossier** : sous-dossier cible pré-rempli (ex. nom du poste, `<homeDirectory>\Sauvegardes\<NomPoste>`), éditable via icône crayon.
- Section **Dossiers à sauvegarder** : aperçu résumé de la sélection courante (ex. « Dossier personnel (NomPoste) » présélectionné) avec accès à l'écran 2 pour la gestion complète (ajout/suppression). Cet écran n'affiche pas les dossiers à ignorer (ils sont gérés exclusivement dans l'écran 2), pour ne pas surcharger la fenêtre principale.

**Écran 2 — Sous-écran « Dossiers » (accessible depuis l'écran 1 via une flèche de retour)**
- Section **Dossiers à sauvegarder** : dossiers connus de l'utilisateur (Documents, Bureau, Images, Favoris — « Dossier personnel » présélectionné) + chemins personnalisés ; ajout via « Add Backed Up Folder… », suppression par icône corbeille sur chaque ligne.
- Section **Dossiers à ignorer** : présélection = Corbeille (`$RECYCLE.BIN`) et `~/Téléchargements` ; ajout de chemins personnalisés et de **motifs** (`*.tmp`, `node_modules`) interprétés par le moteur d'exclusions (EF-05) via « Add Ignored Folder… » ; icône d'information (ⓘ) expliquant la syntaxe des motifs ; suppression par icône corbeille.
- Bouton **« Reset All Folders… »** (mise en évidence, action destructive) : réinitialise dossiers sauvegardés et ignorés aux valeurs par défaut, avec confirmation.
- Retour à l'écran 1 (flèche) : les modifications de l'écran 2 sont conservées en mémoire dans l'état d'édition en cours ; elles ne sont écrites dans le magasin de configuration qu'au clic sur « Sauvegarder » de l'écran 1 (cohérence avec le bouton « Annuler » global, qui doit pouvoir tout abandonner).

**Comportements transverses (inchangés par rapport à la v1.0)**
- **Verrouillage GPO** : si la configuration est gérée par stratégie de groupe (clé `ManagedByGpo`), tous les champs des deux écrans passent en lecture seule avec mention « Géré par votre organisation » — cohérent avec D7.
- **Validation** : « Sauvegarder » (écran 1) écrit le magasin de configuration unique (registre) et notifie le service ; « Annuler » abandonne sans écrire, quel que soit l'écran affiché au moment de l'annulation. Un test de connectivité au partage est proposé avant écriture.
- **Langue** : interface 100 % française, chaînes externalisées pour traduction future (les libellés anglais de la maquette — « New Backup », « Add Backed Up Folder… » — sont des placeholders de prototype, à traduire dans l'implémentation finale).

### EF-04 — Détection des changements (USN Journal) — **modifié en v1.1**
- L'agent interroge le journal USN du volume système via `DeviceIoControl` / `FSCTL_QUERY_USN_JOURNAL` puis `FSCTL_READ_USN_JOURNAL` (lecture sélective par raison de modification et filtrage sur les arborescences cibles).
- Persistance du dernier USN traité par volume : au redémarrage du service, reprise exacte où l'on s'était arrêté.
- **Détection de rotation du journal** : si l'identifiant du journal a changé ou si le dernier USN traité est antérieur au premier USN valide, l'agent déclenche une **sauvegarde complète de référence** des arborescences cibles avant de reprendre le mode incrémental.
- **Dimensionnement initial** : l'agent augmente la taille du journal au premier démarrage (`FSCTL_CREATE_USN_JOURNAL`, valeur par défaut 256 Mo).
- **Dimensionnement dynamique (nouveau v1.1)** : l'agent mesure le débit d'écriture d'enregistrements USN sur les 30 premiers jours d'exploitation et journalise une alerte si la taille configurée couvre moins de 72 h d'activité observée au rythme le plus soutenu constaté. L'administrateur peut ajuster la taille via la configuration (magasin unique) sans réinstallation. Objectif : éviter la découverte de la sous-dimension uniquement après une perte d'enregistrements sur un poste à forte activité disque (IDE, synchronisation tierce en tâche de fond).
- **Alerte proactive avant rotation** : un compteur d'utilisation du journal (pourcentage de la capacité couverte depuis le dernier USN traité) est journalisé à chaque cycle ; un seuil configurable (défaut 80 %) déclenche une alerte Event Log distincte de la bascule en sauvegarde complète, pour permettre une action corrective avant perte de données.

### EF-12 — Résilience aux déconnexions réseau (postes mobiles, Wi-Fi, VPN) — **complété en v1.1**
Principe directeur : **découplage total de la détection (locale) et du transfert (réseau)**. La détection ne dépend jamais de la disponibilité réseau ; le transfert reprend toujours proprement.

- **File d'attente persistante** (SQLite) : tout fichier détecté par le journal USN mais non encore copié y est conservé ; il survit à l'arrêt du service, aux déconnexions et aux redémarrages du poste.
- **Machine à états par fichier** : `PENDING → COPYING → DONE`. Au redémarrage, tout fichier en état `COPYING` repasse en `PENDING` et est recopié intégralement (aucune reprise à mi-fichier, aucun état ambigu).
- **Transfert atomique** : copie vers un fichier temporaire `<nom>.part` sur le partage, puis `rename` final (atomique sur SMB). Un fichier interrompu n'existe jamais sous son nom définitif ; le `.part` orphelin est purgé au prochain cycle.
- **Surveillance réseau avec backoff exponentiel** : 10 s, 30 s, 1 min, 5 min… Pendant l'indisponibilité, l'agent continue de lire le journal USN localement et d'alimenter la file ; à la reconnexion, le retard est rattrapé en une seule vague, dans l'ordre.
- **Coupures brutes du poste** : la base d'état (SQLite WAL + `synchronous=FULL`) est durable et auto-réparatrice ; les fichiers en cours repassent en `PENDING` au redémarrage. Aucune sauvegarde corrompue, aucun fichier oublié.
- **Microcoupures** : l'agent bénéficie gratuitement des *durable handles* SMB3 natifs Windows (reconnexion transparente des handles ouverts). Ils ne constituent pas un mécanisme de reprise fiable : la machine à états SQLite reste le mécanisme principal.
- **Conséquence sur le dimensionnement** : pendant une longue coupure, le journal USN est le seul tampon de détection — le dimensionnement dynamique (EF-04) est donc indispensable.
- **Gestion de la tempête de reconnexion (nouveau v1.1)** : lors d'une panne réseau/WAN généralisée touchant une majorité du parc simultanément, la reprise « en une seule vague » de chaque poste peut saturer le lien vers le serveur de fichiers si tous les postes reprennent au même instant. Mitigation :
  - **Gigue de reprise (jitter)** : chaque agent applique un délai aléatoire (0-15 min, configurable) avant de démarrer sa vague de rattrapage après détection de la reconnexion, pour étaler la charge dans le temps.
  - **Limitation de bande passante par défaut** conservatrice à la reprise (valeur réduite les 10 premières minutes, puis relâchée progressivement si le lien n'est pas saturé), paramétrable par GPO pour s'aligner sur la capacité du lien du site.
  - Cette mitigation est un minimum v1.0 ; un ordonnancement centralisé par site (roadmap v1.1+) reste préférable pour les parcs de grande taille mais n'est pas contractuel ici.

---

## 7. Exigences techniques

*(ET-01, ET-02, ET-03 inchangées par rapport à la v1.0 ; voir CDC v1.0 section 7 pour le texte de référence intégral. Ajout ET-04 ci-dessous.)*

### ET-04 — Signature de code et compatibilité EDR (nouveau v1.1)
| Besoin | Exigence |
|---|---|
| Signature | Installateur (MSI/Inno Setup) et exécutables PyInstaller signés avec un certificat de signature de code valide ; certificat EV recommandé pour limiter les alertes SmartScreen/réputation. |
| Compatibilité EDR | Tests de non-régression contre au moins une solution EDR/antivirus représentative de l'environnement cible avant tout déploiement au-delà du pilote (voir D10). Documenter les exclusions/exceptions éventuellement nécessaires côté EDR pour le service et son compte SYSTEM. |
| Justification | Le profil comportemental de l'agent (service SYSTEM, `SeTcbPrivilege`, `ImpersonateLoggedOnUser`, lecture bas niveau `FSCTL_READ_USN_JOURNAL`) recoupe des heuristiques couramment utilisées pour détecter des ransomwares/infostealers. Sans anticipation, le déploiement GPO risque d'être bloqué silencieusement sur une partie du parc. |

---

## 8. Contraintes et risques techniques identifiés

| Risque | Mitigation |
|---|---|
| Rotation du journal USN (taille par défaut ~32 Mo sur C:) | Dimensionnement initial + **dimensionnement dynamique et alerte proactive (EF-04 v1.1)** + détection d'identifiant de journal changé → sauvegarde complète de référence |
| `FSCTL_READ_USN_JOURNAL` strict sur Windows 10/11 (structures exactes) | Structures packées via `struct` conformes aux en-têtes Microsoft ; tests sur cible 10/11 dès le prototype |
| `vssadmin create` indisponible sur Windows 11 | Utilisation systématique de `Win32_ShadowCopy` (WMI) |
| `wmic` déprécié/retiré des Windows récents | Ne pas dépendre de `wmic` ; appels CIM via PowerShell ou COM |
| Isolation de session (Session 0) : les lecteurs mappés (`Y:`) de l'utilisateur sont invisibles du service | Toujours utiliser le chemin UNC (`homeDirectory`), jamais la lettre de lecteur, après impersonnification |
| `WTSQueryUserToken` exige un processus service exécuté en SYSTEM avec `SeTcbPrivilege` | Architecture conforme (D1) ; aucune alternative par encodage de jeton |
| Cliché VSS unique par volume | Un seul cliché à la fois, verrou interne, suppression garantie (`try/finally`) |
| Espace cible insuffisant | Surveillance et alerte dans le journal ; jamais de blocage du poste |
| **(nouveau) Faux positifs EDR/antivirus sur le comportement du service** | Signature de code + tests de compatibilité préalables (D10, ET-04) |
| **(nouveau) Données stockées en clair sur le partage réseau (pas de chiffrement au repos en v1.0)** | Identifié comme risque actif nécessitant avis écrit du RSSI avant déploiement à grande échelle (D11) ; ACL du dossier personnel AD comme mitigation partielle uniquement — ne couvre pas un accès administrateur du serveur de fichiers compromis |
| **(nouveau) Tempête de reconnexion après panne réseau généralisée** | Gigue de reprise + limitation de bande passante progressive à la reconnexion (EF-12 v1.1) |
| **(nouveau) Impossibilité technique de garantir l'absence de données personnelles dans les arborescences sauvegardées** | Le principe « zéro donnée personnelle sur le poste » (D8) est une politique organisationnelle, pas une garantie technique — l'agent sauvegarde ce qu'il trouve dans les arborescences ciblées. À traiter dans le volet légal (D9, section 9), pas comme un risque purement technique |

---

## 9. Sécurité et conformité — **fortement étoffée en v1.1**

### 9.1 Principes techniques (inchangés)
- **Principe du moindre privilège** : le service est local (`SYSTEM`) ; l'accès réseau s'effectue exclusivement sous l'identité de l'utilisateur connecté (D6). Aucun compte de sauvegarde global.
- **Contenus jamais journalisés** : les logs ne contiennent que des métadonnées (chemins, compteurs, codes erreur), jamais de contenu de fichiers.
- **Intégrité des sauvegardes** : horodatage à la copie ; versions non écrasables par l'utilisateur (ACL du dossier personnel : accès utilisateur + administrateurs, conformément au modèle des home folders AD).

### 9.2 Cadre juridique et RGPD (remplace et détaille l'ancien paragraphe unique de la v1.0)
Ce point est traité ici comme un **prérequis de déploiement**, pas comme une simple mention de conformité :

- **Qualification** : l'agent constitue un traitement automatisé pouvant porter sur des données à caractère personnel (fichiers bureautiques d'un salarié susceptibles de contenir des informations personnelles malgré la politique « zéro donnée perso »). Voir avertissement 1.4.
- **AIPD (Analyse d'Impact relative à la Protection des Données)** : à réaliser ou à faire formellement écarter par le DPO avant tout déploiement, y compris pilote (D9). Ce CDC ne remplace pas cette analyse.
- **Information individuelle des salariés** : au-delà de la charte informatique signée à l'embauche, chaque salarié concerné doit recevoir une information spécifique sur ce dispositif précis (finalité, données concernées, durée de conservation des versions, absence de contournement possible, modalités d'exercice des droits RGPD). Une charte générique ancienne ne suffit pas.
- **Avis du CSE** : requis si l'entreprise compte 50 salariés ou plus (D8, inchangé), à obtenir avant déploiement et non a posteriori.
- **Proportionnalité** : le ciblage strict des arborescences professionnelles (D2) est le principal argument de proportionnalité du dispositif ; il doit être documenté comme tel dans l'AIPD, pas seulement mentionné dans ce CDC.
- **Durée de conservation** : la politique de rétention (EF-08) doit être définie avec une justification métier explicite (et non une valeur technique arbitraire), car elle constitue une durée de conservation de données au sens RGPD.
- **Droits des personnes** : prévoir une procédure (même manuelle en v1.0) permettant de répondre à une demande d'accès/suppression d'un salarié sur ses sauvegardes, notamment après son départ.

### 9.3 Sécurité applicative (nouveau v1.1)
- Signature de code de l'installateur et des exécutables (D10, ET-04).
- Tests de compatibilité EDR/antivirus avant déploiement au-delà du pilote.
- Chiffrement au repos identifié comme risque actif nécessitant avis RSSI écrit avant déploiement à grande échelle (D11), même si non implémenté en v1.0.

---

## 10. Stratégie de recette (nouvelle section v1.1)

La v1.0 définissait des critères d'acceptation sans procédure de vérification associée. Cette section comble ce manque.

### 10.1 Environnement de test
- Environnement de test isolé reproduisant le domaine AD, un partage SMB de test, et au moins un poste Windows 10 et un poste Windows 11 à jour.
- Jeu de données de test incluant : fichiers volumineux, fichiers verrouillés en continu (simulateur), volume d'écriture soutenu pour valider le dimensionnement USN.

### 10.2 Déploiement pilote
- Avant tout déploiement large : pilote sur un groupe restreint de postes volontaires (recommandé : 10 à 20 postes, profils d'usage variés), pendant une durée minimale permettant d'observer un cycle de rotation USN naturel.
- Le pilote est la première étape autorisée après validation D9 (gouvernance légale) — pas avant.
- Procédure de rollback documentée (désinstallation + conservation des données déjà sauvegardées, conformément à EF-11) en cas d'incident sur le pilote.

### 10.3 Vérification des critères d'acceptation
Chaque critère de la section 11 doit être vérifié par un scénario de test explicite et rejoué avant chaque montée de version majeure, pas seulement à la livraison initiale.

---

## 11. Critères d'acceptation v1.1

1. Installation manuelle complète en moins de 10 minutes, sélection d'arborescences incluse.
2. Installation GPO silencieuse au démarrage, sans fenêtre ni interaction.
3. Création/modification d'un fichier dans une arborescence cible → sauvegardé sur le partage avant le délai planifié, utilisateur ouvert ou non (via VSS pour les fichiers ouverts).
4. Fichier hors arborescence ou exclu → jamais copié, présence constatable dans les journaux de décision.
5. Redémarrage du poste/service → reprise exacte au dernier USN traité, sans doublon inutile.
6. Suppression d'un fichier source → versions précédentes toujours présentes sur le partage.
7. Journal de décision consultable (Event Log + fichier local) avec compteurs sauvegardés/ignorés/erreurs.
8. Désinstallation propre (service retiré, aucune donnée de sauvegarde effacée).
9. **(nouveau)** Installateur et service signés numériquement ; aucune alerte bloquante sur l'EDR/antivirus testé (D10).
10. **(nouveau)** Simulation d'activité disque soutenue sur un volume de test → alerte proactive d'utilisation du journal USN déclenchée avant rotation effective (EF-04).
11. **(nouveau)** Simulation d'une coupure réseau généralisée sur le parc pilote → reprise étalée dans le temps (gigue observée), pas de saturation constatée du lien serveur (EF-12).
12. **(nouveau)** AIPD réalisée ou formellement écartée par le DPO, et information individuelle des salariés du pilote effectuée, avant démarrage du pilote (D9).

---

## 12. Roadmap post-v1.1 (non contractuel)

- v1.1.x (extension technique) : extensions multi-volumes, exclusions par modèle avancé, console de supervision.
- v2.0 : cible cloud chiffrée, chiffrement au repos en v1.0-réseau si l'avis RSSI (D11) l'impose avant, restauration assistée, politiques par groupes AD, ordonnancement centralisé de la reprise réseau par site.

---

*Document de référence — toute modification des décisions D1 à D11 exige une révision formelle validée par le porteur du projet. Le déploiement en production, y compris le pilote, est subordonné à la validation du volet 9 par un DPO ou juriste habilité (D9).*
