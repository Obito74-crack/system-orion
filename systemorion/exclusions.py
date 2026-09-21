"""Évaluation des règles d'exclusion (EF-05).

Ignore un fichier si :
- Hors arborescences cibles (D2)
- Extension ou motif exclu (fnmatch)
- Fichier temporaire ou verrouillage système (~$*, *.tmp, .lock)
- Répertoire exclu ($RECYCLE.BIN, node_modules, AppData, .git, etc.)
- Taille nulle non pertinente
- Fichier supprimé avant transfert

Insensible à la casse (spécifique au système de fichiers Windows NTFS).
Compatible Windows et environnements de test Linux (PureWindowsPath).
"""

from __future__ import annotations

import fnmatch
from pathlib import PureWindowsPath

from systemorion.config import expand_path
from systemorion.models import OrionConfig


class ExclusionEngine:
    """Moteur de décision sauvegarder / ignorer (CDC EF-05)."""

    def __init__(self, config: OrionConfig, user_profile: str | None = None) -> None:
        self.user_profile = user_profile
        self._load_rules(config)

    def _load_rules(self, config: OrionConfig) -> None:
        """Charge et prépare les règles de filtrage."""
        # 1. Arborescences cibles sous forme d'objets PureWindowsPath
        self.target_paths: list[PureWindowsPath] = [
            PureWindowsPath(expand_path(p, self.user_profile))
            for p in config.target_paths
        ]

        # 2. Motifs de noms de fichiers (ex: *.tmp, ~$*)
        self.patterns: list[str] = [p.lower() for p in config.exclusion_patterns]

        # 3. Extensions exclues (ex: .tmp, .bak)
        self.extensions: set[str] = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in config.exclusion_extensions
        }

        # 4. Répertoires exclus (comparaison sur les composants du chemin)
        self.excluded_dirs: set[str] = {d.lower() for d in config.excluded_dirs}

    def reload(self, config: OrionConfig, user_profile: str | None = None) -> None:
        """Recharge les règles après une modification de configuration."""
        if user_profile is not None:
            self.user_profile = user_profile
        self._load_rules(config)

    def is_under_target(self, file_path: str) -> bool:
        """Vérifie si le chemin se trouve sous l'une des arborescences cibles autorisées (D2)."""
        try:
            path_obj = PureWindowsPath(file_path)
            for target in self.target_paths:
                if path_obj.is_relative_to(target):
                    return True
        except Exception:
            pass
        return False

    def should_exclude(
        self,
        file_path: str,
        file_size: int | None = None,
        check_target: bool = True,
    ) -> tuple[bool, str]:
        """Évalue si un fichier doit être ignoré.

        Retourne un tuple (exclure: bool, motif: str).
        """
        path_obj = PureWindowsPath(file_path)
        filename = path_obj.name.lower()

        # 1. Vérification appartenance à une arborescence cible (D2)
        if check_target and not self.is_under_target(file_path):
            return (True, "Hors arborescence cible")

        # 2. Vérification des répertoires parents exclus (EF-05, EF-01a)
        # Ex: C:\Users\Alice\Documents\project\node_modules\pkg\index.js -> exclu
        parts = [p.lower() for p in path_obj.parts[:-1]]  # Exclut le nom du fichier
        for part in parts:
            if part in self.excluded_dirs:
                return (True, f"Dossier exclu: {part}")
            # Motifs sur répertoires (ex: .* ou ~*)
            for pat in self.patterns:
                if fnmatch.fnmatch(part, pat):
                    return (True, f"Dossier correspondant au motif exclu: {part} ({pat})")

        # 3. Vérification des extensions exclues
        suffix = path_obj.suffix.lower()
        if suffix in self.extensions:
            return (True, f"Extension exclue: {suffix}")

        # 4. Vérification des motifs de nom de fichier (fnmatch)
        for pattern in self.patterns:
            if fnmatch.fnmatch(filename, pattern):
                return (True, f"Motif de fichier exclu: {pattern}")

        # 5. Fichiers de verrouillage temporaires Office / Windows spécifiques
        if filename.startswith("~$") or filename.startswith(".~"):
            return (True, "Fichier temporaire de verrouillage Office")

        # 6. Vérification de la taille (taille 0 byte non pertinente selon EF-05)
        if file_size is not None and file_size == 0:
            return (True, "Fichier vide (0 octet non pertinent)")

        # Éligible pour sauvegarde
        return (False, "")
