"""File de copie, versioning, reprise réseau, rétention.

Cf. CDC EF-07 (copie réseau), EF-08 (versioning/rétention),
EF-12 (résilience réseau : machine à états PENDING/COPYING/DONE,
écriture atomique .part + rename, backoff exponentiel, gigue de reprise v1.1).

TODO: implémenter la machine à états et la file persistante (state.py).
"""
