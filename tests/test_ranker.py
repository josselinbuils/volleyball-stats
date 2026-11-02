import numpy as np

from volleyball_stats.ranker import features, fit, scores


class TestRanker:
    def test_fit_learns_to_pick_the_right_candidate(self):
        # The right candidate is the one with the bigger second feature, whatever the first.
        rng = np.random.default_rng(0)
        touches = []
        for _ in range(40):
            x = rng.normal(size=(3, 2))
            touches.append((x, int(np.argmax(x[:, 1]))))
        model = fit(touches, steps=500, rate=0.2)

        x = np.array([[5.0, -1.0], [0.0, 2.0], [-3.0, 0.0]])
        assert int(np.argmax(scores(model, x))) == 1

    def test_features_repeat_for_touches_below_the_head(self):
        args = ((100, 150), "pass", (0.0, 0.1, 7), 0.0, 0, (90, 100, 130, 300), 200, 0.2, True, 3.0)
        below = features(*args)
        attack = features(*args[:1], "attack", *args[2:])
        assert len(below) == len(attack) == 34
        assert below[:17] == below[17:] and attack[17:] == [0.0] * 17
