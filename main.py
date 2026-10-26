"""Vision — étape 1 : le cerveau, au terminal.

Pas encore d'audio. On valide ici la seule chose qui compte à ce stade :
l'agent est-il bon, et son texte est-il dicible ?

    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=sk-ant-...        (Windows)
    python main.py
"""

import argparse
import os
import re
import sys
import threading
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
from vision.rapides import JOURS, MOIS, Rapides  # noqa: E402
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

    Les noms sont écrits à la main : passer la locale en français cassait la
    voix, edge-tts lisant avec strptime la date anglaise de son serveur.
    """
    d = datetime.now(timezone.utc)
    return f"{JOURS[d.weekday()]} {d.day:02d} {MOIS[d.month - 1]} {d.year}"


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

# Les recherches suivantes prennent une vingtaine de secondes de plus, et le
# mot d'attente ne se dit qu'une fois : on relance pour que le silence reste
# habité. Formulations différentes — trois fois la même phrase sonnerait plus
# artificiel que le silence lui-même.
RELANCES = (
    "Je croise deux ou trois sources.",
    "Encore un instant, je vérifie.",
    "Presque prêt.",
)
PAUSE_RELANCE = 7.0  # secondes de silence tolérées avant de relancer


class Sortie:
    """Affiche, et parle si la voix est active.

    Le cerveau ne connaît que deux rappels : une phrase est prête, une
    recherche a démarré. Toute la mise en scène est ici, pour qu'il n'ait
    jamais à savoir s'il y a un haut-parleur au bout.
    """

    def __init__(self, voix: Voix | None) -> None:
        self.voix = voix
        self.annonce_faite = False
        self._arret = threading.Event()
        self._veilleur: threading.Thread | None = None

    def nouveau_tour(self) -> None:
        self.annonce_faite = False

    def phrase(self, texte: str) -> None:
        self._taire_les_relances()   # le vrai texte arrive : plus rien à meubler
        print(texte, end=" ", flush=True)
        if self.voix:
            self.voix.dire(texte)

    def recherche(self, numero: int, requete: str | None) -> None:
        if requete is None:
            print(f"\n  … recherche {numero}", end="", flush=True, file=sys.stderr)
            if self.voix and not self.annonce_faite:
                self.annonce_faite = True   # une seule fois par tour
                self.voix.dire(ATTENTE)
                self._lancer_les_relances()
        else:
            print(f" — « {requete} »", end="", flush=True, file=sys.stderr)

    def fin_de_tour(self) -> None:
        self._taire_les_relances()
        if self.voix:
            # ne rends la main qu'une fois la dernière phrase prononcée :
            # sinon l'invite « Vous > » s'affiche pendant qu'il parle encore
            self.voix.attendre()

    # ----------------------------------------------------- relances d'attente

    def _lancer_les_relances(self) -> None:
        self._arret.clear()
        self._veilleur = threading.Thread(target=self._veiller, daemon=True)
        self._veilleur.start()

    def _taire_les_relances(self) -> None:
        self._arret.set()

    def _veiller(self) -> None:
        """Relance tant que le modèle cherche, jamais par-dessus une phrase."""
        i = 0
        while not self._arret.wait(PAUSE_RELANCE):
            if self.voix and not self.voix.occupee():
                self.voix.dire(RELANCES[i % len(RELANCES)])
                i += 1


def main() -> None:
    args = argparse.ArgumentParser(description="Vision — agent d'actualité")
    args.add_argument("--muet", action="store_true",
                      help="sans voix, pour régler le texte plus vite")
    args.add_argument("--voix", default=None, help="nom de voix edge-tts")
    opts = args.parse_args()

    verifier_cle()
    date = aujourdhui()
    cerveau = Cerveau()
    rapides = Rapides(ville_par_defaut=os.environ.get("VISION_VILLE", "Paris"))
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
            if voix:
                voix.fermer()
            return
        if not demande:
            continue

        # Météo, « qui est… », jour férié : une API gratuite répond en une
        # seconde, sans jetons. Sinon, ou au moindre doute, Claude.
        rapide = rapides.repondre(demande)
        if rapide:
            print("\nVision > ", end="", flush=True)
            sortie.nouveau_tour()
            for p in re.split(r"(?<=[.!?])\s+", rapide):
                sortie.phrase(p)
            sortie.fin_de_tour()
            # dans l'historique, pour que la question suivante ait le contexte
            cerveau.historique += [{"role": "user", "content": demande}, {"role": "assistant", "content": rapide}]
            print(f"\n\n[réponse rapide · {duree_parlee(rapide)}]", file=sys.stderr)
            continue

        if premiere:
            demande = f"[Nous sommes le {date}.]\n\n{demande}"
            premiere = False

        print("\nVision > ", end="", flush=True)
        sortie.nouveau_tour()
        try:
            reponse = cerveau.demander(
                demande, sur_phrase=sortie.phrase, sur_recherche=sortie.recherche
            )
            sortie.fin_de_tour()
        except KeyboardInterrupt:
            if voix:
                voix.couper()
            print("\n[interrompu]")
            continue
        print(f"\n\n[{duree_parlee(reponse)}]", file=sys.stderr)


if __name__ == "__main__":
    main()
