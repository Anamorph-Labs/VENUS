import unittest

import numpy as np

from alvenus import voicecaps
from alvenus.voicecaps import from_given, timed


class GivenWordTimes(unittest.TestCase):
    def test_each_caption_word_appears_when_it_is_said(self):
        spoken = [(1.0, 1.2, "he"), (1.2, 1.4, "had"), (1.4, 1.6, "no"), (1.6, 2.1, "answer"),
                  (3.0, 3.3, "so"), (3.3, 3.5, "he"), (3.5, 3.8, "gave")]
        caps = [(0, "He had no answer.", 0.5, 2.8), (1, "So he gave", 2.8, 4.5)]
        out = from_given(caps, spoken)
        self.assertEqual([w.start for w in out[0]], [1.0, 1.2, 1.4, 1.6])
        self.assertEqual([w.start for w in out[1]], [3.0, 3.3, 3.5])
        self.assertAlmostEqual(out[0][-1].end, 2.78)  # the card holds to the cut

    def test_words_the_voice_does_not_say_sit_between_their_neighbours(self):
        spoken = [(1.0, 1.2, "one"), (1.2, 1.4, "for"), (2.0, 2.3, "him")]
        out = from_given([(0, "One for (only) him.", 0.0, 3.0)], spoken)
        s = [w.start for w in out[0]]
        self.assertEqual(s[:2], [1.0, 1.2])
        self.assertTrue(1.4 <= s[2] <= 2.0)
        self.assertEqual(s[3], 2.0)

    def test_a_caption_never_heard_keeps_the_even_spread(self):
        out = from_given([(0, "Silent line", 0.0, 2.0)], [(9.0, 9.2, "other")])
        self.assertNotIn(0, out)

    def test_offset_and_file_shapes(self):
        sb = {"voice_words": [{"start": 0.0, "end": 0.3, "word": "hi"}], "voice_words_at": 14.2}
        self.assertEqual(voicecaps.given_words(sb), [(14.2, 14.5, "hi")])


class SceneTimesAndSwitch(unittest.TestCase):
    def test_a_scenes_own_times_win(self):
        scenes = [{"caption_times": [0.1, 0.9]}]
        out, _ = timed([(0, "Two words", 10.0, 12.0)], {"voice_words": [(0, 1, "two")]}, scenes)
        self.assertEqual([w.start for w in out[0]], [10.1, 10.9])

    def test_switched_off(self):
        out, how = timed([(0, "Two words", 0.0, 2.0)], {"caption_sync": False, "voice_words": [(0.5, 1, "two")]}, [{}])
        self.assertEqual((out, how), ({}, ""))


class HeardFromTheVoice(unittest.TestCase):
    def test_words_land_on_the_syllables(self):
        sr = voicecaps.SR
        a = np.zeros(int(3.0 * sr), dtype=np.float32)
        t = np.arange(int(0.18 * sr)) / sr
        burst = (np.sin(2 * np.pi * 800 * t) * np.hanning(len(t))).astype(np.float32)
        for at in (1.0, 1.5, 2.0):  # three one-syllable words
            i = int(at * sr)
            a[i : i + len(burst)] += burst
        orig = voicecaps.__dict__.get("load_audio")
        import alvenus.media as media

        keep = media.load_audio
        media.load_audio = lambda *_a, **_k: a
        try:
            out = voicecaps.from_voice([(0, "one two three", 0.0, 3.0)], "voice.wav")
        finally:
            media.load_audio = keep
        self.assertIsNone(orig)
        s = [w.start for w in out[0]]
        # each word starts after the syllable before it and by its own syllable
        for got, prev, own in zip(s, (0.0, 1.18, 1.68), (1.0, 1.5, 2.0)):
            self.assertTrue(prev <= got <= own + 0.1, (got, prev, own))


if __name__ == "__main__":
    unittest.main()
