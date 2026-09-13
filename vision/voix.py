"""La voix : synthèse et lecture, en tâche de fond.

Rien de natif à Claude ici — l'API n'a aucune sortie audio. On prend donc
deux briques existantes plutôt que d'en écrire une :

- edge-tts pour la synthèse. Gratuit, sans clé, voix neurales françaises,
  environ 0,3 s jusqu'au premier son (mesuré). Réserve : c'est un client
  non officiel d'un service Microsoft, donc ça peut casser du jour au
  lendemain. Le jour où ça arrive, seule cette classe change.
- pygame.mixer pour la lecture, qui joue du mp3 depuis la mémoire sans
  passer par un fichier temporaire.

Deux fils, pas un. Un seul fil qui synthétise puis joue laisserait un demi-
seconde de blanc entre chaque phrase ; avec deux étages, la phrase suivante
se fabrique pendant que la précédente se joue.
"""

from __future__ import annotations

import asyncio
import io
import os
import queue
import threading

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import edge_tts  # noqa: E402
import pygame  # noqa: E402

# Denise est la plus rapide des voix françaises mesurées (0,30 s contre 1,48 s
# pour les multilingues) et la plus neutre à l'oreille pour de l'information.
VOIX_DEFAUT = "fr-FR-DeniseNeural"

# edge-tts rend du mp3 en 24 kHz : on accorde le mixer dessus.
FREQUENCE = 24000

_FIN = object()  # sentinelle de fermeture


class Voix:
    def __init__(self, voix: str = VOIX_DEFAUT, debit: str = "+8%") -> None:
        self.voix = voix
        # Un poil plus rapide que le débit par défaut : à l'écoute quotidienne,
        # le rythme neutre d'edge-tts traîne un peu pour de l'information.
        self.debit = debit

        pygame.mixer.init(frequency=FREQUENCE)

        self._textes: queue.Queue = queue.Queue()
        self._audios: queue.Queue = queue.Queue()
        self._silence = threading.Event()  # levé = on jette ce qui arrive

        self._synthese = threading.Thread(target=self._boucle_synthese, daemon=True)
        self._lecture = threading.Thread(target=self._boucle_lecture, daemon=True)
        self._synthese.start()
        self._lecture.start()

    # ------------------------------------------------------------------ API

    def dire(self, texte: str) -> None:
        """Met une phrase en file. Ne bloque pas."""
        if texte.strip() and not self._silence.is_set():
            self._textes.put(texte.strip())

    def attendre(self) -> None:
        """Bloque jusqu'à ce que tout soit prononcé."""
        self._textes.join()
        self._audios.join()

    def couper(self) -> None:
        """Arrête net et vide les files. Servira à l'interruption, étape 4."""
        self._silence.set()
        for f in (self._textes, self._audios):
            while not f.empty():
                try:
                    f.get_nowait()
                    f.task_done()
                except queue.Empty:
                    break
        pygame.mixer.music.stop()
        self._silence.clear()

    def fermer(self) -> None:
        self._textes.put(_FIN)
        self._synthese.join(timeout=5)
        self._audios.put(_FIN)
        self._lecture.join(timeout=5)
        pygame.mixer.quit()

    # -------------------------------------------------------------- interne

    def _boucle_synthese(self) -> None:
        boucle = asyncio.new_event_loop()
        asyncio.set_event_loop(boucle)
        while True:
            texte = self._textes.get()
            if texte is _FIN:
                self._textes.task_done()
                return
            try:
                if not self._silence.is_set():
                    self._audios.put(boucle.run_until_complete(self._fabriquer(texte)))
            except Exception as e:  # une phrase perdue ne doit pas tuer la voix
                print(f"[synthèse en échec : {e}]", flush=True)
            finally:
                self._textes.task_done()

    async def _fabriquer(self, texte: str) -> bytes:
        tampon = io.BytesIO()
        com = edge_tts.Communicate(texte, self.voix, rate=self.debit)
        async for morceau in com.stream():
            if morceau["type"] == "audio":
                tampon.write(morceau["data"])
        return tampon.getvalue()

    def _boucle_lecture(self) -> None:
        while True:
            audio = self._audios.get()
            if audio is _FIN:
                self._audios.task_done()
                return
            try:
                if audio and not self._silence.is_set():
                    pygame.mixer.music.load(io.BytesIO(audio))
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy() and not self._silence.is_set():
                        pygame.time.wait(30)
            except Exception as e:
                print(f"[lecture en échec : {e}]", flush=True)
            finally:
                self._audios.task_done()
