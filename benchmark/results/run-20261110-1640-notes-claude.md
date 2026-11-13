# Notation IA (Claude) — run 20261110-1640

Grille par réponse : exactitude / fidélité aux sources / complétude / utilité commerciale, 0-2 chacun → **/8**.

| Q | Type | qwen2.5:1.5b | llama3.2:3b | Commentaire |
|---|---|:-:|:-:|---|
| Q01 | extraction | 2 | 5 | qwen donne la limite rinse-off (1,2 %) au lieu de 0,4 %. llama a la bonne limite mais la mauvaise date pour les produits existants (15/01 au lieu du 15/09/2027). |
| Q02 | extraction | 7 | **0** | llama affirme que le methyl eugenol est interdit dans un shampooing : faux et dangereux commercialement. |
| Q03 | JSON | 5 | 5 | JSON valide et 4 lignes correctes pour les deux, mais les deux transforment les seuils d'étiquetage de la coumarine en limites. |
| Q04 | croisement | 1 | 2 | qwen déclare les 6 produits non conformes. llama se trompe dans les comparaisons (0,9 > 1,2 ; 0,3 > 0,4) et oublie la Crème mains Atelier. |
| Q05 | croisement | 0 | 7 | qwen dit « impacté » (faux). llama compare correctement 0,3 % et 0,4 %. |
| Q06 | e-mail | 3 | 4 | Aucun ne cite le produit concerné ni le délai de 10 semaines. qwen dit que CitruNova « contient moins de citral » alors qu'il n'en contient pas. |
| Q07 | refus | **0** | 8 | qwen invente « 0,01 % » pour le limonène. |
| Q08 | refus | 7 | 5 | llama refuse, puis invente que Verdane est client de Givaudan (contrôle auto : faux négatif). |
| Q09 | fidélité | 1 | 6 | qwen invente une « nouvelle limite » pour la coumarine. llama a raison mais ne mentionne pas l'étiquetage. |
| Q10 | calcul | 1 | 2 | Les deux calculs sont faux (5 % lu comme du citral ; soustraction 0,4 − 0,1). La conclusion « conforme » est juste par hasard. |
| Q11 | résumé FR | 6 | 6 | qwen fait 4 puces au lieu de 3. llama omet l'échéance de septembre 2027. |
| Q12 | priorisation | 2 | 1 | Priorités incohérentes chez les deux. llama répète des lignes et met la Crème mains Atelier, non conforme, en priorité faible. |
| **Total** | | **35/96 (36 %)** | **51/96 (53 %)** | |

## Performances (PC 16 Go)
| | qwen2.5:1.5b | llama3.2:3b |
|---|---|---|
| Vitesse | 18,6 tok/s | 9,5 tok/s |
| Latence moyenne | 8 s | 17,5 s (max 49 s) |
| RAM | 1,2 Go | 2,9 Go |

## Conclusions
1. **Aucun des deux n'est utilisable tel quel** pour un outil commercial : trop d'erreurs factuelles sur des questions simples.
2. **Croisement, comparaison de seuils et calcul échouent chez les deux modèles** (Q04, Q10, Q12). Cela confirme l'architecture : **le code fait la comparaison avec les données clients**, et le LLM se limite à extraire (JSON) puis rédiger.
3. **llama3.2:3b est plus fidèle aux sources** (refus corrects, pas d'invention sur la coumarine), mais il fait des erreurs graves (Q02) et il est 2 fois plus lent.
4. **Le score automatique est peu fiable** : qwen obtient 1,00 sur Q04 et Q12 alors qu'il a tout faux. La relecture par IA est indispensable.
5. Prochaine étape : **qwen2.5:7b**. On s'attend à un bond net en extraction et en fidélité, au prix d'une latence probablement autour de 20–40 s par réponse sur CPU.
