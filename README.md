# Le droit monégasque, modification par modification

**Français** · [English](README.en.md)

<picture>
<source media="(prefers-color-scheme: dark)" srcset="data/fr/effort-dark.svg">
<img alt="Le droit monégasque dans ce dépôt : ce qu’il contient, les modifications par année d’entrée en vigueur, l’exhaustivité au regard des sources officielles et l’exactitude de son contenu" src="data/fr/effort-light.svg" width="880">
</picture>

Fait partie de [lexifina/global-law](https://github.com/lexifina/global-law), un historique git unique pour le droit de chaque pays : ce dépôt contient le droit national monégasque, que global-law lit dans `monaco/national/acts/`.

Deux textes monégasques en dépôt git : la **Constitution du 17 décembre 1962** (avec sa révision de 2002) et la **loi n° 1.362 du 3 août 2009** relative à la lutte contre le blanchiment de capitaux, le financement du terrorisme et la corruption (18 versions consolidées, de 2009 à 2025). Chaque texte modificatif correspond à un commit, attribué à ce texte et daté du jour où ses modifications ont pris effet, à midi à Monaco. Le texte est le texte français de [Legimonaco](https://legimonaco.mc), la base de données juridique officielle de la Principauté.

## Les questions d’un juriste, en commandes git

| Question | Commande |
| --- | --- |
| Que disait l’article 53 de la Constitution le 1er janvier 1990 ? | `python tools/en_vigueur_au.py 1990-01-01 constitution 53` |
| L’article 22-2 de la loi n° 1.362 au 1er janvier 2022 | `python tools/en_vigueur_au.py 2022-01-01 loi-1362 22-2` |
| L’ensemble de la loi n° 1.362 au 1er mars 2019 | `python tools/en_vigueur_au.py 2019-03-01 loi-1362` |
| Quelle loi a écrit chaque ligne d’un article ? | `git blame constitution/article-53.md` |
| Toutes les modifications d’un article, avec la loi qui en est à l’origine | `git log -p --follow loi-1362/article-1er.md` |
| Tout ce qu’une loi a modifié | `git show --stat loi/1549` |
| Toutes les lois qui ont modifié la loi n° 1.362, dans l’ordre | `git log --reverse --format='%(trailers:key=In-force,valueonly,separator=)%x09%an' -- loi-1362` |
| L’état d’un texte un jour où il a été modifié | `git checkout loi-1362/2018-07-07` |
| Ce qu’aucune loi n’explique | `git log --grep='^Kind: ' --format='%h%x09%(trailers:key=In-force,valueonly,separator=)%x09%s'` |

Les lois et leurs dates figurent dans [`lois.csv`](lois.csv) ; les articles de chaque texte, avec le nombre de fois où chacun a été modifié, figurent dans le `README.md` de son dossier. Après une reconstruction de ce dépôt, mettez à jour les anciens clones avec `git fetch --force --tags`.

## Les dates, et celle que nous retenons

Une loi monégasque est datée du jour où le Prince la signe (`Enacted:`), publiée au Journal de Monaco (`Published:`) et opposable aux tiers à compter du lendemain de sa publication (Constitution, art. 69), sauf si elle prévoit une date ultérieure. **Les commits sont datés du jour à partir duquel le texte modifié s’applique** : la date que Legimonaco attribue à la version consolidée (`<text>@YYYY.MM.DD`), qui détermine le texte applicable à une affaire. Lorsque l’historique propre d’un article donne à sa modification un autre jour (« modifié à compter du … ») que la version qui l’imprime, le commit conserve ce jour dans `Law-in-force:`.

**Git ne peut pas enregistrer de dates antérieures à 1970.** Le texte de la Constitution du 17 décembre 1962 est daté du 1970-01-01 ; sa date réelle figure dans le trailer `In-force:` et dans le tag `constitution/1962-12-17`. `tools/en_vigueur_au.py` lit `In-force:` et donne donc le bon texte pour n’importe quel jour.

## Comment il est vérifié

`tools/check_repo.py` relit depuis git chacune des 20 versions au jour à partir duquel elle s’applique et compare chaque fichier, octet par octet, au texte reconstruit à partir de la page Legimonaco de cette version, puis compare l’ensemble du texte, mot pour mot, à la page lue indépendamment de l’analyseur. `tools/test_repo.py` vérifie le blame, le lecteur avant et après des modifications connues, `git log --follow`, les tags, les trailers, les auteurs et chaque commande du tableau ci-dessus. La construction est déterministe : reconstruite à partir des mêmes données, elle donne les mêmes empreintes de commit. Voir [`REPRODUCE.md`](REPRODUCE.md).

## Ce que signifie « auteur »

L’auteur d’un commit est le texte qui a apporté la modification, désigné comme Legimonaco le désigne (`Loi n° 1.462 du 28 juin 2018`), à une adresse qui ne peut pas exister (`loi-1462@legimonaco.invalid`). Ainsi, `git blame` indique, pour chaque ligne, la loi qui l’a écrite en dernier. Chaque article de chaque version Legimonaco comporte un « Historique de consolidation » qui nomme les textes qui l’ont créé, modifié ou abrogé, souvent avec le jour (« remplacé à compter du 30 septembre 2023 par la loi n° 1.549 … »). Une modification est attribuée au seul texte que cet historique nomme pour ce jour, ou au seul texte qu’il nomme pour la première fois (`Evidence:`, dans chaque commit, indique lequel des deux).

Les premières versions ont pour auteurs les textes eux-mêmes. Les modifications qu’aucun texte n’explique à lui seul ont pour auteur `Legimonaco` et sont étiquetées : `Kind: typesetting` lorsque seuls les espacements ont changé, `Kind: reverted` lorsqu’une version imprime de nouveau un texte antérieur, `Kind: unexplained` dans les autres cas, y compris lorsque l’historique nomme conjointement une loi et une ordonnance souveraine pour une même modification. Seul le commit de documentation a pour auteur Lexifina.

## Ce qu’il ne montre pas

- Les intitulés des divisions (Titre, Chapitre, Section ; ils figurent dans le `README.md` de chaque texte), les historiques et les notes éditoriales.
- La Constitution de 1911, que Legimonaco ne propose qu’en PDF joint au texte de 1962, et tout texte autre que ces deux-là.
- Le texte tel que modifié entre deux versions de Legimonaco : l’historique contient exactement les versions que publie Legimonaco, y compris ses propres corrections et celles de ses versions qui impriment une modification par anticipation ou impriment de nouveau un texte antérieur (voir `REPRODUCE.md`).

Il s’agit d’un outil d’aide à la recherche. Seul le Journal de Monaco fait foi ; les textes consolidés de Legimonaco, et donc ce dépôt, ne font pas foi.

## Comment il est construit

`tools/build.py` lit la liste des versions de Legimonaco et la page de chaque version, compare les versions successives article par article, attribue chaque modification et écrit les commits. Aucun modèle d’IA n’intervient dans sa construction ni dans sa vérification. Chaque étape, commande et décision figure dans [`REPRODUCE.md`](REPRODUCE.md). `corpus.json` décrit le corpus pour l’index mondial de Lexifina.

## Licence

Source : Legimonaco, base de données juridique officielle de la Principauté de Monaco (Gouvernement Princier), https://legimonaco.mc. Aux termes de la loi monégasque sur le droit d’auteur, « Les lois, ordonnances, arrêtés, décisions et publications administratives, judiciaires ou officielles ne bénéficient pas de la protection instituée par la présente loi » (Loi n° 491 du 24 novembre 1948, article 38). Les textes ont été convertis en un fichier par article et organisés en commits ; leur libellé n’a pas été modifié. Les contributions propres de Lexifina sont placées sous CC0. Voir [`LICENSE`](LICENSE).

Ceci est une traduction de la version anglaise ([README.en.md](README.en.md)) ; en cas de divergence, la version anglaise fait foi.

## En savoir plus

Dans le dépôt [lexifina/global-law](https://github.com/lexifina/global-law) (pages en anglais) :

- [FEATURES.md](https://github.com/lexifina/global-law/blob/main/FEATURES.md): toutes les fonctionnalités et ce que chaque corpus doit prendre en charge (`git blame`, `law.py`, outils MCP)
- [FAQ.md](https://github.com/lexifina/global-law/blob/main/FAQ.md): questions et réponses · [CONTRIBUTING.md](https://github.com/lexifina/global-law/blob/main/CONTRIBUTING.md): proposer une modification · [MCP.md](https://github.com/lexifina/global-law/blob/main/MCP.md): serveur MCP · [REPRODUCE.md](https://github.com/lexifina/global-law/blob/main/REPRODUCE.md): comment il a été construit · [CHANGELOG.md](https://github.com/lexifina/global-law/blob/main/CHANGELOG.md)
- [FRESHNESS.md](https://github.com/lexifina/global-law/blob/main/FRESHNESS.md): à quel point chaque corpus est à jour · [Surveillance](https://github.com/lexifina/global-law/tree/main/monitoring): si les mises à jour fonctionnent · [WATCHING.md](https://github.com/lexifina/global-law/blob/main/WATCHING.md): comment chaque source officielle est surveillée pour repérer les modifications
- [performance/](https://github.com/lexifina/global-law/tree/main/performance): la rapidité des outils, mesurée
- [visualisations/](https://github.com/lexifina/global-law/tree/main/visualisations): graphiques et liens à travers le droit du monde entier
- [Vulnérabilités](https://github.com/lexifina/global-law/tree/main/vulnerabilities): erreurs dans les textes tels qu’ils ont été publiés
