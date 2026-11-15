# Likeness benchmark

`likeness.py` gives the 3D figures each player's hair (colour, style) and skin, guessed from their card's picture: a
human-parsing model (`mattmdjaga/segformer_b2_clothes`, SegFormer trained on ATR, MIT licence) splits it into hair, face,
arms and legs, and fixed thresholds read their colours and the hair's shape. The review corrects the rest.

```bash
uv run python benchmarks/likeness/bench.py [--show]
```

The labels (`outputs/benchmarks/likeness/truth.json`, real people's looks: never committed) were set by eye on the
review's moments of each player, 15 Nov: 55 players of the three first matches, 53 with a card picture.

| 15 Nov, 53 players | hair colour | hairstyle | skin | skin within a tone | looks that stand out told |
|---|---|---|---|---|---|
| Made-up looks (dark short hair, second tone) | 66% | 53% | 79% | 85% | 0/9 |
| Guessed from the card picture | 74% | 58% | 81% | 87% | 8/9 |

The looks that stand out: a bald or grey head, blond hair, the darkest skin, long loose hair. Not told (the owner's
call: not a big deal): a ponytail, hidden from the front, and the middle skin tones, which the card picture's touch-up
(its contrast evened) and the gym's light mix. A first version parsing every moment of every player (backs turned too)
filled the GPU and froze the PC (15 Nov), for little more on the skin: dropped.
