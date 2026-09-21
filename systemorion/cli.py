"""Interface en ligne de commande d'administration pour System Orion (CLI).

Permet aux administrateurs systèmes et au support technique de :
- Consulter l'état du service, de la configuration et de la file d'attente (status).
- Déclencher un cycle de sauvegarde immédiat (backup-now).
- Lister les versions sauvegardées d'un fichier (list-versions).
- Restaurer une version en ligne de commande (restore).
- Tester la résolution Active Directory (test-ad).
"""

from __future__ import annotations

import argparse
import os
import sys

from systemorion.cible_ad import (
    AdDirectoryResolver,
    AdsiDirectoryResolver,
    MockAdDirectoryResolver,
)
from systemorion.config import ConfigManager
from systemorion.restore import find_backup_versions, restore_file
from systemorion.state import StateDB


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} o"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} Mo"


def cmd_status(args: argparse.Namespace) -> int:
    """Affiche l'état général de System Orion (configuration, file, base SQLite)."""
    cfg_mgr = ConfigManager()
    config = cfg_mgr.load()

    print("=" * 60)
    print("  System Orion — État du système et configuration")
    print("=" * 60)

    # 1. Configuration
    print("\n[Configuration active]")
    print(f"  • Verrouillé par GPO : {'Oui (Lecture seule)' if config.managed_by_gpo else 'Non (Local)'}")
    print(f"  • Cible UNC configurée : {config.unc_override or 'Résolution dynamique Active Directory'}")
    print(f"  • Sous-dossier cible : {config.backup_subfolder}")
    print(f"  • Intervalle de cycle : {config.cycle_interval_s} secondes")
    print(f"  • Rétention : {config.retention_max_versions} versions max / {config.retention_max_days} jours max")
    print(f"  • Dossiers surveillés ({len(config.target_paths)}) :")
    for tp in config.target_paths:
        print(f"      - {tp}")
    print(f"  • Exclusions : {len(config.exclusion_patterns)} motifs, {len(config.excluded_dirs)} dossiers")

    # 2. Base SQLite et file d'attente
    print("\n[Base d'état SQLite et files d'attente]")
    db_path = config.state_db_path
    if os.path.exists(db_path):
        try:
            state_db = StateDB(db_path)
            counts = state_db.get_queue_counts()
            print(f"  • Fichier SQLite : {db_path} (Présent)")
            print(f"  • Transferts en attente (PENDING) : {counts.get('PENDING', 0)}")
            print(f"  • Transferts en cours (COPYING)   : {counts.get('COPYING', 0)}")
            print(f"  • Transferts terminés (DONE)      : {counts.get('DONE', 0)}")
            print(f"  • Transferts en échec (FAILED)    : {counts.get('FAILED', 0)}")
            state_db.close()
        except Exception as e:
            print(f"  • Erreur de lecture de la base d'état : {e}")
    else:
        print(f"  • Base d'état SQLite non initialisée ({db_path})")

    print("\n" + "=" * 60)
    return 0


def cmd_test_ad(args: argparse.Namespace, resolver: AdDirectoryResolver | None = None) -> int:
    """Interroge Active Directory et affiche le homeDirectory résolu (EF-03)."""
    if resolver is None:
        resolver = AdsiDirectoryResolver() if sys.platform == "win32" else MockAdDirectoryResolver()
    domain = os.environ.get("USERDOMAIN", "DOMAINE")
    user = os.environ.get("USERNAME", "Utilisateur")

    print(f"Interrogation Active Directory pour {domain}\\{user}...")
    home_dir = args.mock_home if getattr(args, "mock_home", None) else resolver.get_user_home_directory(domain, user)

    if home_dir:
        print(f"[OK] homeDirectory résolu : {home_dir}")
        from systemorion.cible_ad import resolve_backup_destination

        dest_unc = resolve_backup_destination(
            r"C:\Users\Utilisateur\Documents\test.txt",
            r"C:\Users\Utilisateur\Documents",
            home_dir,
            computer_name=os.environ.get("COMPUTERNAME", "PC-CLIENT"),
            subfolder_name="SystemOrion",
        )
        print(f"[OK] Exemple de chemin de sauvegarde UNC calculé : {dest_unc}")
        return 0
    else:
        print(f"[AVERTISSEMENT] Aucun attribut homeDirectory trouvé pour {domain}\\{user}.")
        return 1


def cmd_list_versions(args: argparse.Namespace) -> int:
    """Liste les versions archivées d'un fichier."""
    source_path = args.file_path
    cfg_mgr = ConfigManager()
    config = cfg_mgr.load()

    state_db = None
    if os.path.exists(config.state_db_path):
        try:
            state_db = StateDB(config.state_db_path)
        except Exception:
            pass

    versions = find_backup_versions(
        source_path=source_path,
        state_db=state_db,
        backup_search_dir=config.unc_override,
    )

    if state_db is not None:
        state_db.close()

    print(f"\nVersions archivées pour : {source_path}")
    print("-" * 75)
    if not versions:
        print("  Aucune version trouvée.")
        print("-" * 75)
        return 0

    print(f"  {'#':<3} | {'Date & Heure':<19} | {'Taille':<10} | {'Emplacement sauvegardé'}")
    print("-" * 75)
    for idx, v in enumerate(versions, start=1):
        dt_str = v.backed_up_at.strftime("%d/%m/%Y %H:%M:%S")
        size_str = _format_size(v.file_size)
        print(f"  {idx:<3} | {dt_str:<19} | {size_str:<10} | {v.dest_path}")

    print("-" * 75)
    print(f"Total : {len(versions)} version(s) archivée(s).\n")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Restaure un fichier sauvegardé vers une destination."""
    version_dest_path = args.source_backup
    target_dest = args.destination or os.getcwd()
    overwrite = args.overwrite

    try:
        result = restore_file(version_dest_path, target_dest, overwrite=overwrite)
        print(f"[OK] Fichier restauré avec succès dans : {result.restored_path}")
        print(f"     Taille : {_format_size(result.file_size)}")
        if result.version_timestamp:
            print(f"     Horodatage de version d'origine : {result.version_timestamp.strftime('%d/%m/%Y %H:%M')}")
        return 0
    except Exception as e:
        print(f"[ERREUR] Échec de la restauration : {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="systemorion",
        description="Outil d'administration en ligne de commande pour System Orion.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # status
    subparsers.add_parser("status", help="Affiche l'état du système et de la configuration")

    # test-ad
    p_test_ad = subparsers.add_parser("test-ad", help="Teste la résolution Active Directory du homeDirectory")
    p_test_ad.add_argument("--mock-home", help="Chemin UNC simulé pour tester la résolution sans contrôleur de domaine")

    # list-versions
    p_list = subparsers.add_parser("list-versions", help="Liste les versions archivées d'un fichier")
    p_list.add_argument("file_path", help="Chemin du fichier source local")

    # restore
    p_restore = subparsers.add_parser("restore", help="Restaure un fichier sauvegardé")
    p_restore.add_argument("source_backup", help="Chemin complet du fichier versionné sauvegardé")
    p_restore.add_argument(
        "--destination", "-d", help="Dossier ou chemin cible de restauration (défaut: dossier courant)"
    )
    p_restore.add_argument("--overwrite", action="store_true", help="Écrase le fichier existant si présent")

    return parser


def main(argv: list[str] | None = None, resolver: AdDirectoryResolver | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 0

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "status":
        return cmd_status(args)
    elif args.command == "test-ad":
        return cmd_test_ad(args, resolver=resolver)
    elif args.command == "list-versions":
        return cmd_list_versions(args)
    elif args.command == "restore":
        return cmd_restore(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
