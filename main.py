"""Vision — étape 1 : le cerveau, au terminal.

Pas encore d'audio. On valide ici la seule chose qui compte à ce stade :
l'agent est-il bon, et son texte est-il dicible ?

    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=sk-ant-...        (Windows)
    python main.py
"""

import locale
from datetime import datetime, timezone

from vision.cerveau import Cerveau


def aujourdhui() -> str:
    """La date, en clair, pour l'injecter dans le premier message.

    Le modèle ne connaît pas la date de façon fiable, et un briefing calé sur
    la mauvaise semaine est pire qu'aucun briefing.
    """
    try:
        locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
    except locale.Error:
        pass  # la locale française n'est pas installée : on garde l'anglais
    return datetime.now(timezone.utc).strftime("%A %d %B %Y")


def parler(phrase: str) -> None:
    """L'étape 2 remplacera cette fonction par la synthèse vocale.

    Tout le reste du programme est déjà écrit pour ça : le cerveau livre des
    phrases complètes au fil de l'eau, pas un bloc final.
    """
    print(phrase, end=" ", flush=True)


def main() -> None:
    date = aujourdhui()
    cerveau = Cerveau()
    print(f"— Vision. Nous sommes le {date}. Ctrl+C pour sortir.")

    premiere = True
    while True:
        try:
            demande = input("\n\nVous > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nÀ demain.")
            return
        if not demande:
            continue

        if premiere:
            demande = f"[Nous sommes le {date}.]\n\n{demande}"
            premiere = False

        print("\nVision > ", end="", flush=True)
        try:
            cerveau.demander(demande, sur_phrase=parler)
        except KeyboardInterrupt:
            print("\n[interrompu]")


if __name__ == "__main__":
    main()
