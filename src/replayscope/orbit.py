"""Kaggle Orbit Wars replay adapter; all signals are descriptive, not causal."""


class ReplayError(ValueError):
    pass


def _snapshot(observation, players):
    ships, production, counts = [0] * players, [0] * players, [0] * players
    for planet in observation["planets"]:
        if not isinstance(planet, (list, tuple)) or len(planet) < 7:
            raise ReplayError("Malformed planet")
        owner, amount, produced = int(planet[1]), int(planet[5]), int(planet[6])
        if amount < 0 or produced < 0:
            raise ReplayError("Negative ships or production")
        if 0 <= owner < players:
            ships[owner] += amount
            production[owner] += produced
            counts[owner] += 1
    for fleet in observation.get("fleets", []):
        if not isinstance(fleet, (list, tuple)) or len(fleet) < 7:
            raise ReplayError("Malformed fleet")
        owner, amount = int(fleet[1]), int(fleet[6])
        if amount < 0:
            raise ReplayError("Negative fleet size")
        if 0 <= owner < players:
            ships[owner] += amount
    return ships, production, counts


def analyze(payload, slot):
    """Return per-slot metrics from a Kaggle steps[turn][player] replay."""
    if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
        raise ReplayError("Expected object containing steps array")
    steps = payload["steps"]
    if not steps or not isinstance(steps[0], list):
        raise ReplayError("Empty replay")
    players = len(steps[0])
    if players not in (2, 4) or type(slot) is not int or slot not in range(players):
        raise ReplayError("Invalid player count or player slot")

    final, final_turn = None, None
    timeline, milestones, signals = [], {}, []
    previously_owned = {}
    high_production_losses = 0

    for turn, entries in enumerate(steps):
        if not isinstance(entries, list) or len(entries) != players:
            raise ReplayError("Inconsistent players across turns")
        observations = []
        for entry in [entries[slot]] + entries[:slot] + entries[slot + 1:]:
            if isinstance(entry, dict):
                obs = entry.get("observation")
                if isinstance(obs, dict) and isinstance(obs.get("planets"), list):
                    observations.append(obs)
        if not observations:
            continue
        obs = observations[0]
        try:
            ships, production, counts = _snapshot(obs, players)
            owned = {int(p[0]): int(p[6]) for p in obs["planets"] if int(p[1]) == slot}
        except (ValueError, TypeError, IndexError, OverflowError) as exc:
            raise ReplayError("Invalid replay observation values") from exc

        for planet in obs["planets"]:
            planet_id = int(planet[0])
            if int(planet[1]) != slot and previously_owned.get(planet_id, 0) >= 4:
                high_production_losses += 1
        previously_owned = owned
        own = {"turn": turn, "ships": ships[slot], "production": production[slot],
               "planets": counts[slot]}
        if turn % 10 == 0:
            timeline.append(own)
        if turn in (25, 50, 80, 110):
            milestones[str(turn)] = {**own, "production_gap_to_leader": max(production) - production[slot]}
        final, final_turn = (ships, production, counts), turn

    if final is None:
        raise ReplayError("No readable board observations")
    ships, production, counts = final
    if not timeline or timeline[-1]["turn"] != final_turn:
        timeline.append({"turn": final_turn, "ships": ships[slot],
                         "production": production[slot], "planets": counts[slot]})
    rank = 1 + sum(s > ships[slot] for s in ships)
    outcome = ("win" if ships[slot] == max(ships) and ships.count(max(ships)) == 1
               else "draw" if ships[slot] == max(ships) else "loss")
    if milestones.get("80", {}).get("production_gap_to_leader", 0) >= 10:
        signals.append("production_gap_ge_10_at_turn_80")
    if high_production_losses:
        signals.append("lost_production_4_or_5_planet")
    return {
        "format": "orbit_wars", "mode": f"{players}P", "turns": final_turn,
        "player_slot": slot, "final_score": ships[slot], "all_final_scores": ships,
        "final_production": production[slot], "final_planets": counts[slot],
        "rank": rank, "top_two": rank <= 2, "outcome": outcome,
        "lost_high_production_planets": high_production_losses,
        "signals": signals, "milestones": milestones, "timeline": timeline,
    }
