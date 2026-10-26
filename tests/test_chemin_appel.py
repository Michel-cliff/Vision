"""Exerce le chemin d'appel complet sans toucher a l'API.

Ce test existe parce qu'un NameError est passe en production : la classe
Sortie avait ete testee isolement, jamais branchee au cerveau.
"""
import sys, types, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from vision.cerveau import Cerveau
from main import Sortie


def ev(type_, **kw):
    o = types.SimpleNamespace(type=type_)
    for k, v in kw.items():
        setattr(o, k, v)
    return o


class FauxFlux:
    """Rejoue une sequence d'evenements de la meme forme que le SDK."""
    def __init__(self, evenements):
        self.evenements = evenements
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter(self.evenements)
    def get_final_message(self):
        return types.SimpleNamespace(content=[], usage=types.SimpleNamespace(
            input_tokens=0, output_tokens=0))


class FauxClient:
    def __init__(self, evenements):
        self.messages = types.SimpleNamespace(
            stream=lambda **kw: FauxFlux(evenements))


def principal():
    outil = types.SimpleNamespace(type="server_tool_use", input={"query": "actualite IA"})
    evenements = [
        ev("content_block_start", content_block=outil),
        ev("content_block_stop", content_block=outil),
        ev("text", text="Première phrase. "),
        ev("text", text="M. Macron a parlé. "),
        ev("text", text="Fin sans point final"),
    ]
    dites, recherches = [], []

    class SortieEspionne(Sortie):
        def phrase(self, t): dites.append(t)
        def recherche(self, n, q): recherches.append((n, q))

    s = SortieEspionne(voix=None)
    s.nouveau_tour()
    c = Cerveau(client=FauxClient(evenements))
    reponse = c.demander("test", sur_phrase=s.phrase, sur_recherche=s.recherche)
    s.fin_de_tour()

    attendu_phrases = ["Première phrase.", "M. Macron a parlé.", "Fin sans point final"]
    assert dites == attendu_phrases, f"phrases inattendues : {dites}"
    assert recherches == [(1, None), (1, "actualite IA")], f"recherches : {recherches}"
    assert c.historique[-1]["role"] == "assistant"
    assert "M. Macron" in reponse

    print("phrases livrees :", dites)
    print("recherches vues :", recherches)
    print("\nOK — chemin d'appel complet, abreviation preservee")


def date_sans_locale():
    """La date en français ne doit pas changer la locale du programme.

    setlocale(fr) cassait la voix : edge-tts lit la date anglaise de son
    serveur (« Mon, 26 Oct ») avec strptime, qui suit la locale.
    """
    import time
    from main import aujourdhui
    texte = aujourdhui()
    assert any(j in texte for j in ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")), texte
    time.strptime("Mon, 26 Oct 2026 10:21:02", "%a, %d %b %Y %H:%M:%S")
    print("OK — date en français, locale intacte :", texte)


if __name__ == "__main__":
    principal()
    date_sans_locale()
