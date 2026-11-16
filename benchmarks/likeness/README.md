# Likeness benchmark

`likeness.py` gives the 3D figures each player's hair (colour, style) and skin, guessed from their card's picture: a
human-parsing model (`mattmdjaga/segformer_b2_clothes`, SegFormer trained on ATR, MIT licence) splits it into hair, face,
arms and legs, and fixed thresholds read their colours and the hair's shape. A head going bald keeps short hair of its
colour; none is bald: hair the picture does not show is short and black (the owner's rule, 16 Nov, after a player with
hair at the back was made bald). The benchmark's numbers did not move: none of its 53 players was guessed bald. The Names tab sets the figure, a man's or a woman's.

```bash
uv run python benchmarks/likeness/bench.py [--show]
```

The labels (`outputs/benchmarks/likeness/truth.json`, real people's looks: never committed) were set by eye on the
review's moments of each player, 15 Nov: 55 players of the three first matches, 53 with a card picture.

| 16 Nov, 53 players | hair colour | hairstyle | skin | skin within a tone | looks that stand out told |
|---|---|---|---|---|---|
| Made-up looks (dark short hair, second tone) | 66% | 60% | 79% | 85% | 0/5 |
| Guessed from the card picture | 72% | 60% | 81% | 87% | 5/5 |

The looks that stand out: a bald head (none of the 53: those going bald count as short; never guessed since 16 Nov), grey or blond hair, the darkest
skin, long loose hair. A beard and the figure were tried too, from the card picture with the parsing model and SigLIP:
neither told well enough (the figure set by hand instead, the beard left out). Not told (the owner's
call: not a big deal): a ponytail, hidden from the front, and the middle skin tones, which the card picture's touch-up
(its contrast evened) and the gym's light mix. A first version parsing every moment of every player (backs turned too)
filled the GPU and froze the PC (15 Nov), for little more on the skin: dropped.
