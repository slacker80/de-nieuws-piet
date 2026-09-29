"""Guard: de verplichte lokale suite is feitelijk volledig gedraaid.

Alfabetisch het laatste testbestand, zodat deze controle ná alle andere tests
wordt uitgevoerd. Een sessie waarin één of meer tests zijn overgeslagen
(missing Docker/npm, ontbrekend artefact, al actieve hoofdstack) mag nooit als
"volledig gedraaid" doorgaan: dat zou een misleidende voltooiing zijn.

Bij een mislukking meldt de assertie precies wát er is overgeslagen.
"""

from __future__ import annotations

from tests import runtime_env


def test_lokale_suite_zonder_overgeslagen_tests() -> None:
    """Geen enkele test in deze sessie is overgeslagen."""
    assert runtime_env.skipped_tests == [], (
        "de lokale suite is NIET volledig gedraaid; overgeslagen:\n"
        + "\n".join(runtime_env.skipped_tests)
    )
