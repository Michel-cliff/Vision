"""Vision — étape 1 : le cerveau, au terminal.

Pas encore d'audio. On valide ici la seule chose qui compte à ce stade :
l'agent est-il bon, et son texte est-il dicible ?

    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=sk-ant-...        (Windows)
    python main.py
"""

import locale
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

# Sous Windows la console est en cp1252 : sans ça, tout le français de l'agent
# sort en charabia — accents, guillemets et tirets cadratins compris.
for flux in (sys.stdout, sys.stderr):
    if hasattr(flux, "reconfigure"):
        flux.reconfigure(encoding="utf-8", errors="replace")

# Chargé avant l'import du cerveau : le client Anthropic lit la variable
# d'environnement à sa construction.
load_dotenv()

from vision.cerveau import Cerveau  # noqa: E402


def verifier_cle() -> None:
    """Échouer tôt, avec une phrase utile plutôt qu'une pile d'appels.

    Sans clé, le SDK lève une TypeError d'une douzaine de lignes au moment de
    construire la requête — un message qui ne dit pas quoi faire.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    print(
        "Aucune clé API trouvée.\n\n"
        "Crée un fichier .env à la racine du projet, avec dedans :\n"
        "    ANTHROPIC_API_KEY=sk-ant-...\n\n"
        "Il est déjà ignoré par git. Sinon, en une fois :\n"
        "    ANTHROPIC_API_KEY=sk-ant-... ./.venv/Scripts/python.exe main.py",
        file=sys.stderr,
    )
    raise SystemExit(1)


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


# Débit d'un journaliste radio en français. Sert à mesurer, pas à prédire
# au mot près : ce qu'on veut savoir, c'est « est-ce qu'on tient la minute ».
MOTS_PAR_MINUTE = 155


def duree_parlee(texte: str) -> str:
    mots = len(texte.split())
    secondes = round(mots / MOTS_PAR_MINUTE * 60)
    verdict = "ok" if secondes <= 70 else "trop long"
    return f"{mots} mots, environ {secondes} s à voix haute — {verdict}"


def parler(phrase: str) -> None:
    """L'étape 2 remplacera cette fonction par la synthèse vocale.

    Tout le reste du programme est déjà écrit pour ça : le cerveau livre des
    phrases complètes au fil de l'eau, pas un bloc final.
    """
    print(phrase, end=" ", flush=True)


def main() -> None:
    verifier_cle()
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
            reponse = cerveau.demander(demande, sur_phrase=parler)
        except KeyboardInterrupt:
            print("\n[interrompu]")
            continue
        print(f"\n\n[{duree_parlee(reponse)}]", file=sys.stderr)


if __name__ == "__main__":
    main()
