# Vision

Un agent d'actualité vocal. On lui parle, il cherche, il répond à voix haute.

Help keep you updated.

## Où on en est

| Étape | État | Ce que ça fait |
|---|---|---|
| **1. Le cerveau** | ✅ | Claude + recherche web, diffusé phrase par phrase |
| **2. La voix** | ✅ | Il parle, phrase par phrase, pendant que la suite s'écrit |
| 3. L'oreille | à venir | Micro → texte |
| 4. La conversation | à venir | Historique, interruption, reprise |
| 5. Le confort | à venir | Qualité de voix, déploiement |

## Lancer l'étape 1

```bash
python -m venv .venv
pip install -r requirements.txt
```

Puis, sans rien activer — ça marche dans n'importe quel shell :

```bash
ANTHROPIC_API_KEY=sk-ant-... ./.venv/Scripts/python.exe main.py   # Git Bash
```

Si tu préfères activer l'environnement, la commande dépend du shell. Sous
Windows, `\` est un séparateur pour cmd mais un caractère d'échappement pour
Git Bash — s'y tromper donne `.venvScriptsactivate: command not found` :

| Shell | Activation | Variable |
|---|---|---|
| Git Bash | `source .venv/Scripts/activate` | `export CLE=...` |
| cmd.exe | `.venv\Scripts\activate` | `set CLE=...` |
| PowerShell | `.venv\Scripts\Activate.ps1` | `$env:CLE = "..."` |
| macOS / Linux | `source .venv/bin/activate` | `export CLE=...` |

Puis demande-lui « briefing du matin ».

## Avant de committer

```bash
./.venv/Scripts/python.exe -m ruff check --select F,E9 .
./.venv/Scripts/python.exe tests/test_chemin_appel.py
```

Les deux existent parce qu'un `NameError` est passé en production : la classe
`Sortie` avait été testée isolément, jamais branchée au cerveau. Ruff attrape
les noms non définis, le test rejoue le chemin d'appel complet avec un faux
client — sans toucher à l'API, donc gratuit et instantané.

## Comment c'est fait

```
main.py            boucle terminal, met en scène (affiche et/ou parle)
vision/prompt.py   le prompt système — le vrai produit, isolé pour son historique git
vision/cerveau.py  l'appel Claude, la diffusion, le découpage en phrases
vision/voix.py     synthèse et lecture, en tâche de fond
```

Le cerveau ne connaît que deux rappels : « une phrase est prête », « une
recherche a démarré ». Il ignore s'il y a un haut-parleur au bout — c'est
`main.py` qui décide. D'où le mode `--muet`, qui sert à régler le texte sans
attendre qu'il finisse de parler.

## La voix

Rien de natif à Claude : l'API n'a aucune sortie audio. On prend donc deux
briques existantes.

**edge-tts** pour la synthèse — gratuit, sans clé, voix neurales françaises,
mesuré à 0,30 s jusqu'au premier son avec `fr-FR-DeniseNeural` (contre 1,48 s
pour les voix multilingues, écartées pour ça). Réserve honnête : c'est un
client non officiel d'un service Microsoft, ça peut casser du jour au
lendemain. Le jour où ça arrive, seul `vision/voix.py` change — et le
remplaçant documenté par Anthropic est ElevenLabs.

**pygame.mixer** pour la lecture, qui joue le mp3 depuis la mémoire sans
fichier temporaire.

Deux fils, pas un : un seul fil qui synthétise puis joue laisserait un demi-
seconde de blanc entre chaque phrase. Avec deux étages, la phrase suivante se
fabrique pendant que la précédente se joue.

### Meubler l'attente

Pendant les recherches, aucun texte n'est produit — vingt à trente secondes de
silence. L'agent dit « Je regarde ça » au démarrage, puis relance toutes les
sept secondes tant que rien n'arrive, avec des formulations différentes : trois
fois la même phrase sonnerait plus artificiel que le silence.

Une relance ne part jamais par-dessus une phrase en cours (`Voix.occupee`) —
sinon l'agent se coupe la parole. Elle s'arrête net dès que le vrai texte
arrive.

C'est l'application qui parle, pas le modèle. Le prompt interdit au modèle
d'annoncer ses recherches, parce que venant de lui c'est du remplissage. Mais
à l'oral le silence est pire — et l'application, elle, sait exactement quand
une requête part.

### Régler la longueur

Le prompt disait « vise cent cinquante mots, pas plus de deux cents » : le
modèle rendait cent quatre-vingt-dix-huit. Donner une fourchette fait viser le
haut — il s'ancre sur le plus grand nombre énoncé. Un seul plafond, plus bas,
présenté comme un plafond et non comme une cible.

### Trois décisions structurantes

**L'API Claude n'a pas d'audio.** Ni entrée ni sortie. La voix de claude.ai
n'existe pas côté API. Il faut donc trois briques distinctes : reconnaissance
vocale, Claude, synthèse vocale. On construit celle du milieu en premier.

**Le découpage en phrases est l'architecture, pas un détail.** Le cerveau livre
chaque phrase dès qu'elle est complète, au lieu d'attendre le dernier token.
C'est ce qui permettra, à l'étape 2, de commencer à parler pendant que la
réponse s'écrit encore. Le cookbook d'Anthropic mesure environ 31 % de latence
perçue en moins rien qu'avec la diffusion.

**Le texte doit être dicible.** Pas de markdown, pas de puces, pas d'URL. Une
liste à puces lue à voix haute est insupportable, et une URL épelée est absurde.
Ça se décide dans le prompt, dès maintenant — pas à l'étape 5.

### Deux pièges déjà traités

`M. Macron` ne doit pas se couper après le point : `vision/cerveau.py` tient une
liste d'abréviations françaises, sinon la voix marque un temps au milieu du nom.
Contrepartie assumée : une phrase qui finit vraiment par `etc.` reste collée à
la suivante — un bloc un peu long, jamais une coupure fausse.

Les outils serveur ne lèvent pas d'exception. Une recherche en échec revient en
HTTP 200 avec un objet d'erreur dans le bloc de résultat. Sans contrôle explicite,
l'agent répondrait de mémoire et personne ne le verrait.

## Modèle

`claude-sonnet-5`. Le cookbook d'Anthropic recommande Haiku pour la latence,
mais sur un tour avec recherche la latence vient de la recherche, pas du modèle —
et juger de la fiabilité d'une source est exactement ce qu'un petit modèle fait
mal. Haiku n'a d'ailleurs pas accès à la version récente de `web_search`.

Pas de `temperature` : le paramètre est rejeté en 400 sur les modèles actuels.
`output_config.effort` le remplace.
