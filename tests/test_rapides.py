"""Les réponses rapides, sans réseau : chaque API est remplacée par sa réponse type.

Lancer : ./.venv/Scripts/python.exe tests/test_rapides.py
"""
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from vision.rapides import Rapides  # noqa: E402

LYON = [{"lat": "45.76", "lon": "4.83", "name": "Lyon", "display_name": "Lyon, Rhône, France"}]
METEO = {
    "current": {"temperature_2m": 17.6, "weather_code": 3},
    "daily": {
        "time": ["2026-10-26", "2026-10-27"],
        "weather_code": [3, 61],
        "temperature_2m_max": [19.2, 14.8],
        "temperature_2m_min": [9.1, 8.4],
        "precipitation_probability_max": [10, 80],
    },
}
WIKI = {"type": "standard", "title": "Fela Kuti",
        "extract": "Fela Anikulapo Kuti est un musicien nigérian. Il est le créateur de l'afrobeat. Il meurt en 1997."}
AMBIGU = {"type": "disambiguation", "title": "Mercure", "extract": "Mercure peut désigner…"}
FERIES = [{"date": "2026-11-01", "localName": "Toussaint"}, {"date": "2026-11-11", "localName": "Armistice"}]


def faux_web(urls_vues):
    def obtenir(url):
        urls_vues.append(url)
        if "nominatim" in url:
            return LYON
        if "open-meteo" in url:
            return METEO
        if "wikipedia" in url:
            return AMBIGU if "Mercure" in url else WIKI
        if "date.nager.at" in url:
            return FERIES
        raise AssertionError(f"URL inattendue : {url}")
    return obtenir


def principal():
    vues = []
    r = Rapides(obtenir=faux_web(vues), ville_par_defaut="Paris", aujourdhui=lambda: date(2026, 10, 26))

    # météo, avec un lieu et un jour
    rep = r.repondre("Quel temps fera-t-il demain à Lyon ?")
    assert rep and "Lyon" in rep and "demain" in rep and "15" in rep and "pluie" in rep.lower(), rep
    assert any("open-meteo" in u for u in vues)

    # une question sur la pluie donne toujours le risque, même faible
    rep = r.repondre("Va-t-il pleuvoir à Lyon ?")
    assert rep and "10 pour cent" in rep, rep

    # météo sans lieu : la ville par défaut, maintenant
    vues.clear()
    rep = r.repondre("il fait combien dehors ?")
    assert rep and "18" in rep, rep
    assert any("q=Paris" in u for u in vues), vues

    # qui est : le résumé Wikipédia, deux phrases au plus
    rep = r.repondre("Qui est Fela Kuti ?")
    assert rep == "Fela Anikulapo Kuti est un musicien nigérian. Il est le créateur de l'afrobeat.", rep

    # page d'homonymie : on rend la main à Claude
    assert r.repondre("C'est quoi Mercure ?") is None

    # jour férié
    rep = r.repondre("C'est quand le prochain jour férié ?")
    assert rep and "Toussaint" in rep and "1er novembre" in rep, rep

    # tout le reste va à Claude, y compris l'actualité d'une personne
    for q in ("Quoi de neuf aujourd'hui ?", "Qui est le nouveau Premier ministre ?", "Résume l'actu tech"):
        assert r.repondre(q) is None, q

    # une API en panne : on rend la main, sans lever
    def panne(url):
        raise OSError("réseau coupé")
    assert Rapides(obtenir=panne).repondre("Quel temps à Lyon ?") is None

    print("OK — météo, wikipédia, jours fériés, et la main rendue à Claude quand il faut")


if __name__ == "__main__":
    principal()
