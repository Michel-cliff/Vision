"""Les réponses rapides : ce qui n'a pas besoin de Claude ni d'une recherche web.

La météo, « qui est… / c'est quoi… » et le prochain jour férié se répondent
avec une API gratuite et sans clé, en une seconde au lieu de quinze, sans
consommer de jetons. Tout le reste, et tout cas douteux, revient à Claude :
`repondre` rend None dès qu'il n'est pas sûr (page d'homonymie, lieu introuvable,
API en panne). Une mauvaise réponse rapide coûterait plus cher qu'une lente.

APIs (annuaire public-apis) : Nominatim pour le lieu, Open-Meteo pour la météo,
Wikipédia pour les résumés, Nager.Date pour les jours fériés.
"""

import json
import re
import ssl
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date

import certifi

# Le magasin Windows que lit Python garde ici une racine périmée : Wikipédia et
# OpenStreetMap sortaient en « certificate has expired ». certifi, déjà installé
# avec le SDK Anthropic, a les racines à jour.
TLS = ssl.create_default_context(cafile=certifi.where())

# Nominatim exige un User-Agent qui identifie l'application.
AGENT = "Vision/0.1 (assistant vocal personnel)"
DELAI = 6  # secondes : au-delà, Claude répondra aussi vite

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

# Codes météo WMO, comme Open-Meteo les rend.
CIEL = [
    ((0,), "ciel dégagé"), ((1, 2), "quelques nuages"), ((3,), "ciel couvert"),
    ((45, 48), "brouillard"), ((51, 53, 55, 56, 57), "bruine"),
    ((61, 63, 65, 66, 67), "pluie"), ((71, 73, 75, 77), "neige"),
    ((80, 81, 82), "averses"), ((85, 86), "averses de neige"), ((95, 96, 99), "orage"),
]

METEO = re.compile(
    r"m[ée]t[ée]o|quel temps|il fait (combien|chaud|froid|beau)|pleuvoir|pleut|temp[ée]rature|parapluie",
    re.IGNORECASE,
)
# Le lieu commence par une majuscule : « à Lyon », « sur Marseille », « pour Saint-Étienne ».
LIEU = re.compile(r"\b(?:à|a|sur|pour|en|au)\s+([A-ZÀ-Ý][\w\-' ]*?)(?=\s+(?:demain|aujourd|après|ce |cette )|\s*[?.!]*$)")
# « qui est Fela Kuti », « c'est quoi Mercure » : un nom propre seulement. Un sujet
# qui commence par une minuscule (« le nouveau Premier ministre ») est de
# l'actualité, et Wikipédia y serait en retard : il va à Claude.
# La casse n'est ignorée que dans la tournure, pas dans la majuscule du sujet.
QUI = re.compile(
    r"^\s*(?i:qui (?:est|était|etait)|c'?est quoi|qu'?est[- ]ce que c'?est que?|qu'?est[- ]ce que)\s+([A-ZÀ-Ý][^?]*?)\s*\?*\s*$"
)
FERIE = re.compile(r"jours? f[ée]ri[ée]s?", re.IGNORECASE)


def _ciel(code: int) -> str:
    return next((nom for codes, nom in CIEL if code in codes), "temps variable")


def _date_dite(d: date) -> str:
    jour = "1er" if d.day == 1 else str(d.day)
    return f"le {JOURS[d.weekday()]} {jour} {MOIS[d.month - 1]}"


def _http_json(url: str):
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(requete, timeout=DELAI, context=TLS) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


class Rapides:
    def __init__(
        self,
        obtenir: Callable[[str], object] = _http_json,
        ville_par_defaut: str = "Paris",
        aujourdhui: Callable[[], date] = date.today,
    ) -> None:
        self.obtenir = obtenir
        self.ville = ville_par_defaut
        self.aujourdhui = aujourdhui

    def repondre(self, demande: str) -> str | None:
        """Une réponse prête à dire, ou None pour laisser Claude répondre."""
        try:
            if FERIE.search(demande):
                return self._ferie()
            if m := QUI.match(demande):
                return self._wikipedia(m.group(1))
            if METEO.search(demande):
                return self._meteo(demande)
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return None  # réseau, API ou réponse inattendue : Claude prend le relais
        return None

    # ------------------------------------------------------------------ météo

    def _meteo(self, demande: str) -> str | None:
        m = LIEU.search(demande)
        lieu = m.group(1).strip() if m else self.ville
        bas = demande.lower()
        jour = 2 if "après-demain" in bas or "apres-demain" in bas else 1 if "demain" in bas else 0

        q = urllib.parse.urlencode({"q": lieu, "format": "json", "limit": 1, "accept-language": "fr"})
        trouves = self.obtenir(f"https://nominatim.openstreetmap.org/search?{q}")
        if not trouves:
            return None
        lat, lon = trouves[0]["lat"], trouves[0]["lon"]
        q = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "Europe/Paris", "forecast_days": 3,
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        })
        m = self.obtenir(f"https://api.open-meteo.com/v1/forecast?{q}")
        d = m["daily"]
        bas_, haut = round(d["temperature_2m_min"][jour]), round(d["temperature_2m_max"][jour])
        pluie = d.get("precipitation_probability_max", [None] * 3)[jour]
        # Le risque se dit quand il compte, ou quand c'est la question posée.
        sur_la_pluie = re.search(r"pleu|pluie|parapluie", bas) is not None
        risque = f" Risque de pluie : {pluie} pour cent." if pluie is not None and (pluie >= 40 or sur_la_pluie) else ""
        if jour == 0:
            maintenant = round(m["current"]["temperature_2m"])
            ciel = _ciel(m["current"]["weather_code"])
            return f"À {lieu}, il fait {maintenant} degrés, {ciel}. Aujourd'hui, entre {bas_} et {haut} degrés.{risque}"
        quand = "après-demain" if jour == 2 else "demain"
        return f"À {lieu} {quand} : {_ciel(d['weather_code'][jour])}, entre {bas_} et {haut} degrés.{risque}"

    # -------------------------------------------------------------- wikipédia

    def _wikipedia(self, sujet: str) -> str | None:
        titre = urllib.parse.quote(sujet.strip().replace(" ", "_"))
        page = self.obtenir(f"https://fr.wikipedia.org/api/rest_v1/page/summary/{titre}")
        if page.get("type") != "standard" or not page.get("extract"):
            return None  # homonymie ou page absente : Claude saura demander lequel
        phrases = re.split(r"(?<=[.!?])\s+", page["extract"].strip())
        return " ".join(phrases[:2])

    # ---------------------------------------------------------- jours fériés

    def _ferie(self) -> str | None:
        auj = self.aujourdhui()
        for annee in (auj.year, auj.year + 1):
            for f in self.obtenir(f"https://date.nager.at/api/v3/PublicHolidays/{annee}/FR"):
                d = date.fromisoformat(f["date"])
                if d >= auj:
                    quand = "aujourd'hui" if d == auj else _date_dite(d)
                    return f"Le prochain jour férié : {f['localName']}, {quand}."
        return None
