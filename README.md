# Vision

Un agent d'actualité vocal. On lui parle, il cherche, il répond à voix haute.

Help keep you updated.

## Où on en est

| Étape | État | Ce que ça fait |
|---|---|---|
| **1. Le cerveau** | ✅ | Claude + recherche web, diffusé phrase par phrase, au terminal |
| 2. La voix | à venir | Synthèse vocale branchée sur le découpage déjà en place |
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

## Comment c'est fait

```
main.py            boucle terminal, injecte la date, appelle le cerveau
vision/prompt.py   le prompt système — le vrai produit, isolé pour son historique git
vision/cerveau.py  l'appel Claude, la diffusion, le découpage en phrases
```

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
