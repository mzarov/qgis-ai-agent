import unittest

from qgis_ai_agent.qgis_tools.processing.ranking import EXACT, score


def haystack(name, bare="", tags="", group=""):
    return {
        "name": name.lower(),
        "id": f"native:{bare or name.replace(' ', '').lower()}",
        "bare": (bare or name.replace(" ", "")).lower(),
        "tags": tags.lower(),
        "group": group.lower(),
    }


def best(entries, query):
    terms = query.lower().split()
    ranked = sorted(
        ((score(item, terms, query.lower()), item["bare"]) for item in entries), reverse=True
    )
    return [name for weight, name in ranked if weight > 0]


class RankingTest(unittest.TestCase):
    def test_exact_identifier_wins_outright(self):
        plain = haystack("Buffer", "buffer")
        self.assertEqual(score(plain, ["buffer"], "buffer"), EXACT)

    def test_plain_tool_beats_its_elaborate_cousins(self):
        entries = [
            haystack("Tapered buffers", "taperedbuffer"),
            haystack("Multi-ring buffer (constant distance)", "multiringconstantbuffer"),
            haystack("Buffer", "buffer"),
        ]
        self.assertEqual(best(entries, "buffer")[0], "buffer")

    def test_stem_matches_a_longer_word(self):
        entries = [haystack("Line intersections", "lineintersections", tags="intersection")]
        self.assertTrue(best(entries, "intersect"))

    def test_longer_word_matches_a_shorter_stem(self):
        entries = [haystack("Centroids", "centroids")]
        self.assertTrue(best(entries, "centroid"))

    def test_short_stems_do_not_match_loosely(self):
        entries = [haystack("Voronoi polygons", "voronoipolygons")]
        self.assertEqual(best(entries, "vor"), ["voronoipolygons"])
        self.assertEqual(best(entries, "polygonxyz"), [])

    def test_shorter_name_wins_on_a_tie(self):
        entries = [
            haystack("Dissolve", "dissolve"),
            haystack("Dissolve boundaries between adjacent polygons", "dissolveadjacent"),
        ]
        self.assertEqual(best(entries, "dissolve")[0], "dissolve")

    def test_every_term_counts(self):
        entries = [
            haystack("Merge vector layers", "mergevectorlayers"),
            haystack("Merge lines", "mergelines"),
        ]
        self.assertEqual(best(entries, "merge layers")[0], "mergevectorlayers")

    def test_tags_are_weaker_than_the_name(self):
        by_name = haystack("Clip", "clip")
        by_tag = haystack("Extract by extent", "extractbyextent", tags="clip cut")
        self.assertGreater(score(by_name, ["clip"], "clip"), score(by_tag, ["clip"], "clip"))

    def test_nothing_matching_scores_zero(self):
        self.assertEqual(score(haystack("Buffer", "buffer"), ["ндви"], "ндви"), 0)

    def test_group_alone_is_a_weak_hint(self):
        only_group = haystack("Something else", "somethingelse", group="Vector overlay")
        self.assertGreater(score(only_group, ["overlay"], "overlay"), 0)


if __name__ == "__main__":
    unittest.main()
