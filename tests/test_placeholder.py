"""Point de départ des tests. Cf. CDC section 10 (Stratégie de recette).

Chaque critère d'acceptation (section 11 du CDC) doit correspondre à terme
à un scénario de test explicite, rejoué à chaque montée de version majeure.
"""


def test_smoke():
    import systemorion
    assert systemorion.__version__ == "0.1.0"
