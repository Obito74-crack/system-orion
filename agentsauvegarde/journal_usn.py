"""Requête USN Journal, filtrage, reprise, détection de rotation.

Cf. CDC EF-04 (détection dynamique + alerte proactive avant rotation, v1.1)
et section 8 (risques : rotation du journal, structures FSCTL strictes).

TODO: DeviceIoControl / FSCTL_QUERY_USN_JOURNAL / FSCTL_READ_USN_JOURNAL (pywin32 + struct).
"""
