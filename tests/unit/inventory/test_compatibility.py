from buildcompiler.inventory import RouteScore


def test_route_score_prefers_fewer_missing_domestications():
    assert RouteScore(missing_domestications=0).sort_key() < RouteScore(missing_domestications=1).sort_key()


def test_route_score_prefers_fewer_missing_lvl1_plasmids():
    assert RouteScore(missing_lvl1_plasmids=0).sort_key() < RouteScore(missing_lvl1_plasmids=1).sort_key()


def test_route_score_uses_stable_identity_tiebreak():
    assert RouteScore(identity_tiebreak=("a",)).sort_key() < RouteScore(identity_tiebreak=("b",)).sort_key()
