# Structure

| Dossier | Contenu |
| --- | --- |
| `constitution/` | La Constitution du 17 décembre 1962 |
| `codes/<code>/<livre>/` | Les codes (`codes/code-civil/`, `codes/code-penal/`, `codes/code-procedure-civile/`, `codes/code-procedure-penale/`, `codes/code-commerce/` ...), un sous-dossier par livre ou titre de premier rang (`codes/code-civil/livre-i/`) |
| `lois/<année>/<numéro>-<objet>/` | Les lois, par année et numéro, ex. `lois/1963/729-concernant-le-contrat-de-travail/` |
| `ordonnances-lois/<année>/<numéro>-<objet>/` | Les ordonnances-lois |
| `ordonnances-souveraines/<année>/<numéro>-<objet>/` | Les ordonnances souveraines |
| `arretes-ministeriels/<année>/<numéro>-<objet>/` | Les arrêtés ministériels |
| `arretes-municipaux/`, `arretes-directoriaux/`, `decisions-ministerielles/`, `decisions-souveraines/`, `decisions/`, `autres-textes-reglementaires/` | Les autres textes réglementaires, même schéma `<année>/<numéro>-<objet>/` |
| `traites/<année>/<mm-jj>-<titre>/` | Les traités et accords internationaux publiés par Legimonaco |

Quand un texte n'a pas de numéro, le dossier commence par le mois et le jour du texte (`05-05-...`). Chaque texte a un
fichier par article (`article-1er.md`, `article-4-bis.md`), `intitule.md`, `preambule.md` (visas) et un `README.md`
(nature, date, publication au Journal de Monaco, adresse Legimonaco de la version). Un texte sans articles garde son
corps dans `texte.md`. Aucun dossier ne contient plus de 1 000 entrées.

## Dates

Legimonaco publie chaque version consolidée d'un texte à sa propre adresse, `<texte>@AAAA.MM.JJ`, datée du jour à
compter duquel elle s'applique. Chaque version est un commit daté de 12 h (heure de Monaco) ce jour-là, repris dans le
trailer `In-force:` (`In-force-basis: legimonaco-version-date`). Avant 1970, que git ne sait pas enregistrer, le commit
est daté du 1er janvier 1970 et le jour réel figure dans le sujet et dans `In-force:`. Les versions applicables après
le jour de la construction sont retenues (non publiées). Aucune date n'est le jour du téléchargement.

Auteur du commit : le texte lui-même pour son texte d'origine ; pour une version modifiée, l'acte que l'historique de
consolidation nomme à cette date (ou, à défaut, le seul acte nouvellement nommé) ; sinon l'éditeur, Legimonaco. Une
version « Texte abrogé » retire le dossier (`Kind: repeal`), attribuée à l'acte abrogeant quand la page le nomme.
