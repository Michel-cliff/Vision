"""Le cerveau : Claude + recherche web, diffusé phrase par phrase.

Le découpage en phrases est le point clé de l'architecture. À l'étape 2, le TTS
se branchera dessus : on commence à parler dès la première phrase terminée, au
lieu d'attendre le dernier token. Le cookbook d'Anthropic mesure environ 31 %
de latence perçue en moins rien qu'avec la diffusion.
"""

import re
import sys
from collections.abc import Callable

import anthropic

from .prompt import SYSTEME

# Sonnet 5 plutôt que Haiku : sur un tour avec recherche, la latence vient de la
# recherche, pas du modèle. Juger de la fiabilité d'une source est précisément ce
# qu'un petit modèle fait mal — et Haiku n'a pas accès au web_search récent.
MODELE = "claude-sonnet-5"

# À l'oral, une réponse longue est une punition : on ne peut ni survoler
# ni relire.
MAX_TOKENS = 1200

# Un briefing monde + France avec recoupement consomme beaucoup de requêtes.
# À 8, l'agent s'arrêtait en plein travail et rendait un tour d'horizon creux
# en s'en excusant — le symptôme ressemblait à un défaut de prompt, c'était
# un budget trop court.
MAX_USES = 20

OUTILS = [
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": MAX_USES,
        "user_location": {
            "type": "approximate",
            "country": "FR",
            "timezone": "Europe/Paris",
        },
    }
]

# Le point final suivi d'une espace, d'un guillemet fermant ou de rien.
FIN_DE_PHRASE = re.compile(r"[.!?…]+[\s»\"']*")

# Un point qui suit l'une de ces abréviations ne termine pas une phrase.
# Sans ce garde-fou, « M. Macron » se coupe en deux et la voix marque un temps
# au milieu du nom — et sur un fil d'actualité français, ça arrive sans cesse.
ABREVIATIONS = frozenset(
    "M Mme Mlle MM Dr Pr St Ste etc cf av ap art p pp no n° éd vol ch fig".split()
)


# Le code d'erreur seul ne dit pas quoi faire. Celui-ci s'est présenté comme
# un défaut de prompt — l'agent rendait un briefing creux en s'en excusant —
# alors que c'était seulement un budget de recherches trop court.
DIAGNOSTICS = {
    "max_uses_exceeded": (
        f"budget de {MAX_USES} recherches épuisé, la réponse est incomplète. "
        f"Augmente MAX_USES dans vision/cerveau.py."
    ),
}


def _est_vraie_fin(fragment: str) -> bool:
    """Le point qui termine `fragment` clôt-il réellement une phrase ?"""
    avant = fragment.rstrip(".!?… \t»\"'")
    dernier = re.split(r"[\s(\[«]", avant)[-1] if avant else ""
    return dernier.strip(".") not in ABREVIATIONS


class Cerveau:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.historique: list[dict] = []

    def demander(self, message: str, sur_phrase: Callable[[str], None]) -> str:
        """Un tour de conversation.

        `sur_phrase` est appelée dès qu'une phrase est complète. À l'étape 1
        elle affiche ; à l'étape 2 elle parlera.
        """
        self.historique.append({"role": "user", "content": message})

        tampon = ""
        phrases: list[str] = []

        def livrer(texte: str) -> None:
            texte = texte.strip()
            if texte:
                phrases.append(texte)
                sur_phrase(texte)

        # Pas de `temperature` : le paramètre est rejeté en 400 sur les modèles
        # actuels. `effort` le remplace, et `medium` suffit à l'oral.
        with self.client.messages.stream(
            model=MODELE,
            max_tokens=MAX_TOKENS,
            system=SYSTEME,
            tools=OUTILS,
            output_config={"effort": "medium"},
            messages=self.historique,
        ) as flux:
            for morceau in flux.text_stream:
                tampon += morceau
                depuis = 0
                while m := FIN_DE_PHRASE.search(tampon, depuis):
                    if _est_vraie_fin(tampon[: m.end()]):
                        livrer(tampon[: m.end()])
                        tampon, depuis = tampon[m.end():], 0
                    else:
                        # abréviation : on saute ce point et on cherche le suivant
                        depuis = m.end()
            livrer(tampon)
            final = flux.get_final_message()

        self._verifier_recherches(final)
        self.historique.append({"role": "assistant", "content": " ".join(phrases)})
        return " ".join(phrases)

    @staticmethod
    def _verifier_recherches(final: anthropic.types.Message) -> None:
        """Les outils serveur ne lèvent pas d'exception.

        Une recherche en échec revient en HTTP 200, dans un bloc de résultat :
        contenu = liste si ça a marché, objet d'erreur sinon. Sans ce contrôle,
        l'agent répond de mémoire et personne ne le voit.
        """
        for bloc in final.content:
            if bloc.type == "web_search_tool_result" and not isinstance(bloc.content, list):
                code = getattr(bloc.content, "error_code", "inconnu")
                detail = DIAGNOSTICS.get(code, "")
                print(f"\n[recherche en échec : {code}] {detail}", file=sys.stderr)

    @staticmethod
    def cout(final: anthropic.types.Message) -> str:
        u = final.usage
        return f"{u.input_tokens} entrée / {u.output_tokens} sortie"
