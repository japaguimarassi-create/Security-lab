from __future__ import annotations

import json

from klod.game_agent import ChessGame, DraughtsGame, GreedyOpponent, RandomOpponent, ReinforcementTrainer, SparsePolicyNetwork, play_match


def main() -> None:
    network = SparsePolicyNetwork()
    initial = network.diagnostics()
    network.adjust_from_error("missed_capture")
    network.adjust_from_error("hung_piece")
    network.adjust_from_error("missed_promotion")
    chess = play_match(ChessGame(), network, RandomOpponent(71), neural_side=1, max_plies=100)
    checkers = play_match(DraughtsGame(), network, GreedyOpponent(), neural_side=1, max_plies=220)
    post_test_adjustments = []
    for error in sorted(set((chess.error_flags or []) + (checkers.error_flags or []))):
        post_test_adjustments.append(network.adjust_from_error(error).__dict__)
    if checkers.termination == "terminal_position" and checkers.winner is None:
        post_test_adjustments.append(network.adjust_from_error("failed_to_progress").__dict__)
    chess_retest = play_match(ChessGame(), network, RandomOpponent(72), neural_side=1, max_plies=100)
    checkers_retest = play_match(DraughtsGame(), network, GreedyOpponent(), neural_side=1, max_plies=220)
    before_rl = network.output_weights
    episodes = ReinforcementTrainer(network, workers=4, seed=91).run(episodes_per_game=2, max_plies=100)
    report = {
        "initial_network": initial,
        "initial_manual_adjustments": [change.__dict__ for change in network.changes[:3]],
        "first_evaluation": {"chess": chess.__dict__, "checkers": checkers.__dict__},
        "post_test_adjustments": post_test_adjustments,
        "retest": {"chess": chess_retest.__dict__, "checkers": checkers_retest.__dict__},
        "reinforcement": {
            "episodes": len(episodes),
            "wins": sum(result.reward > 0 for result in episodes),
            "losses": sum(result.reward < 0 for result in episodes),
            "draws_or_limits": sum(result.reward == 0 for result in episodes),
            "opponents": sorted({result.opponent for result in episodes}),
            "parallel_workers": 4,
            "weights_changed": before_rl != network.output_weights,
            "final_output_weights": network.output_weights,
        },
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
