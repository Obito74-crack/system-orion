"""Persistance SQLite : USN traité, file d'attente, machine à états, historique.

Cf. CDC ET-01 : sqlite3 (stdlib), mode WAL + synchronous=FULL pour durabilité
après coupure. Cf. EF-12 pour la machine à états PENDING/COPYING/DONE.

TODO: schéma des tables (usn_progress, transfer_queue, backup_history).
"""
