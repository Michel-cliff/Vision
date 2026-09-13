"""Vision — étape 1 : le cerveau, au terminal.

Pas encore d'audio. On valide ici la seule chose qui compte à ce stade :
l'agent est-il bon, et son texte est-il dicible ?

    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=sk-ant-...        (Windows)
    python main.py
"""

import argparse
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
from vision.voix import Voix  # noqa: E402


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


# Ce que l'agent dit pendant qu'il cherche. C'est l'application qui le dit,
# pas le modèle : le prompt interdit au modèle d'annoncer ses recherches, parce
# que venant de lui c'est du remplissage. Mais à l'oral, quinze secondes de
# silence sont pires — et l'application, elle, sait qu'une requête est partie.
ATTENTE = "Je regarde ça."


class Sortie:
    """Affiche, et parle si la voix est active.

    Le cerveau ne connaît que deux rappels : une phrase est prête, une
    recherche a démarré. Toute la mise en scène est ici, pour qu'il n'ait
    jamais à savoir s'il y a un haut-parleur au bout.
    """

    def __init__(self, voix: Voix | None) -> None:
        self.voix = voix
        self.annonce_faite = False

    def nouveau_tour(self) -> None:
        self.annonce_faite = False

    def phrase(self, texte: str) -> None:
        print(texte, end=" ", flush=True)
        if self.voix:
            self.voix.dire(texte)

    def recherche(self, numero: int, requete: str | None) -> None:
        if requete is None:
            print(f"\n  … recherche {numero}", end="", flush=True, file=sys.stderr)
            if self.voix and not self.annonce_faite:
                self.annonce_faite = True   # une seule fois par tour
                self.voix.dire(ATTENTE)
        else:
            print(f" — « {requete} »", end="", flush=True, file=sys.stderr)

    def fin_de_tour(self) -> None:
        if self.voix:
            # ne rends la main qu'une fois la dernière phrase prononcée :
            # sinon l'invite « Vous > » s'affiche pendant qu'il parle encore
            self.voix.attendre()


def main() -> None:
    args = argparse.ArgumentParser(description="Vision — agent d'actualité")
    args.add_argument("--muet", action="store_true",
                      help="sans voix, pour régler le texte plus vite")
    args.add_argument("--voix", default=None, help="nom de voix edge-tts")
    opts = args.parse_args()

    verifier_cle()
    date = aujourdhui()
    cerveau = Cerveau()
    voix = None if opts.muet else Voix(**({"voix": opts.voix} if opts.voix else {}))
    sortie = Sortie(voix)
    etat = "muet" if opts.muet else f"voix {voix.voix}"
    print(f"— Vision. Nous sommes le {date}. [{etat}] Ctrl+C pour sortir.")

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
            reponse = cerveau.demander(
                demande, sur_phrase=parler, sur_recherche=montrer_recherche
            )
        except KeyboardInterrupt:
            print("\n[interrompu]")
            continue
        print(f"\n\n[{duree_parlee(reponse)}]", file=sys.stderr)


if __name__ == "__main__":
    main()
