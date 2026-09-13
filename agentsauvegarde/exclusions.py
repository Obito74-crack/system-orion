"""Évaluation des règles d'exclusion (EF-05).

Ignore si : hors arborescences cibles, extension/motif exclu, fichier temporaire
ou verrouillage système, taille nulle non pertinente, répertoire exclu.

TODO: moteur de motifs (fnmatch) chargé depuis config.py.
"""
