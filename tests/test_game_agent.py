from klod.game_agent import ChessGame, DraughtsGame, NetworkSpec, ReinforcementTrainer, SparsePolicyNetwork, play_match
from klod.game_agent.runner import GreedyOpponent, RandomOpponent
from klod.game_agent.games import ChessMove, ChessState


def test_requested_topology_is_recorded_without_allocating_dense_tensor():
    network = SparsePolicyNetwork()
    report = network.diagnostics()
    assert report["requested_topology"] == "4096x2048"
    assert report["requested_dense_parameters"] > 17_000_000_000
    assert report["runtime_parameters"] == 1140
    assert report["active_experts"] == 4
    assert report["router_active_experts_per_action"] == 2


def test_manual_priors_reward_captures_and_penalize_hanging_pieces():
    network = SparsePolicyNetwork()
    weights = network.output_weights
    assert weights["capture_value"] > 1.0
    assert weights["exposed_piece"] < -1.0
    assert weights["promotion_value"] > weights["center_delta"]


def test_error_feedback_changes_only_the_responsible_output_parameter():
    network = SparsePolicyNetwork()
    before = network.output_weights
    change = network.adjust_from_error("hung_piece", severity=2.0)
    after = network.output_weights
    assert change.feature == "exposed_piece"
    assert after["exposed_piece"] < before["exposed_piece"]
    for feature in after:
        if feature != "exposed_piece":
            assert after[feature] == before[feature]


def test_chess_initial_position_has_twenty_legal_moves():
    game = ChessGame()
    state = game.initial_state()
    assert len(game.legal_actions(state)) == 20
    assert not game.in_check(state)


def test_chess_rejects_illegal_move_and_accepts_e4():
    game = ChessGame()
    state = game.initial_state()
    assert game.action_label(next(move for move in game.legal_actions(state) if move.uci() == "e2e4")) == "e2e4"
    try:
        game.apply(state, ChessMove(52, 20))
    except ValueError:
        pass
    else:
        raise AssertionError("e2e5 must be rejected")


def test_chess_castling_moves_the_rook_and_king():
    game = ChessGame()
    board = [""] * 128
    board[116] = "K"
    board[119] = "R"
    board[4] = "k"
    state = ChessState(tuple(board), 1, "K")
    castle = next(move for move in game.legal_actions(state) if move.uci() == "e1g1")
    after = game.apply(state, castle)
    assert after.board[118] == "K"
    assert after.board[117] == "R"
    assert "K" not in after.castling


def test_chess_en_passant_removes_the_captured_pawn():
    game = ChessGame()
    state = game.initial_state()
    for uci in ("e2e4", "a7a6", "e4e5", "d7d5"):
        move = next(move for move in game.legal_actions(state) if move.uci() == uci)
        state = game.apply(state, move)
    en_passant = next(move for move in game.legal_actions(state) if move.uci() == "e5d6")
    assert en_passant.flag == "ep"
    after = game.apply(state, en_passant)
    assert after.board[parse_test_square("d5")] == ""


def parse_test_square(square):
    return (8 - int(square[1])) * 16 + ord(square[0]) - ord("a")


def test_chess_promotion_generates_all_four_piece_choices():
    game = ChessGame()
    board = [""] * 128
    board[116] = "K"
    board[4] = "k"
    board[16] = "P"
    state = ChessState(tuple(board), 1, "")
    promotions = [move for move in game.legal_actions(state) if move.uci().startswith("a7a8")]
    assert {move.promotion for move in promotions} == {"q", "r", "b", "n"}
    queen = next(move for move in promotions if move.promotion == "q")
    assert game.apply(state, queen).board[0] == "Q"


def test_network_policy_gradient_updates_routed_expert_heads():
    network = SparsePolicyNetwork()
    first = [0.0] * 16
    second = [0.0] * 16
    first[0] = 1.0
    second[3] = 1.0
    gradient = network.policy_gradient([first, second], 0, 1.0)
    assert len(gradient) == 4
    assert all(len(row) == 16 for row in gradient)
    assert any(value != 0.0 for row in gradient for value in row)
    before = network.output_weights
    network.apply_output_gradient(gradient)
    assert network.output_weights != before


def test_checkers_multi_capture_is_one_legal_action():
    game = DraughtsGame()
    board = [0] * 64
    board[40] = 1
    board[33] = -1
    board[19] = -1
    state = type(game.initial_state())(tuple(board), 1)
    move = next(move for move in game.legal_actions(state) if move.path == (40, 26, 12))
    assert move.captures == 2
    after = game.apply(state, move)
    assert after.board[12] == 1
    assert after.board[33] == 0 and after.board[19] == 0


def test_checkers_initial_position_and_mandatory_capture_rule():
    game = DraughtsGame()
    state = game.initial_state()
    assert len(game.legal_actions(state)) == 7
    board = [0] * 64
    board[5 * 8 + 0] = 1
    board[4 * 8 + 1] = -1
    board[2 * 8 + 3] = -1
    state = type(state)(tuple(board), 1)
    legal = game.legal_actions(state)
    assert legal
    assert all(move.captures for move in legal)


def test_repetition_feature_flags_an_action_that_returns_to_a_seen_position():
    game = DraughtsGame()
    state = game.initial_state()
    action = game.legal_actions(state)[0]
    successor = game.apply(state, action)
    features = game.features(state, action, {game.state_key(successor)})
    assert features[11] == 1.0


def test_matches_execute_for_both_games():
    network = SparsePolicyNetwork()
    chess = play_match(ChessGame(), network, RandomOpponent(3), max_plies=40)
    checkers = play_match(DraughtsGame(), network, GreedyOpponent(), max_plies=40)
    assert chess.game == "chess" and chess.plies > 0
    assert checkers.game == "checkers" and checkers.plies > 0
    assert checkers.termination in {"terminal_position", "ply_limit", "repetition_draw"}
    assert isinstance(checkers.error_flags, list)


def test_parallel_reinforcement_runs_against_multiple_opponents_and_updates_weights():
    network = SparsePolicyNetwork()
    before = network.output_weights
    trainer = ReinforcementTrainer(network, workers=2, seed=5)
    results = trainer.run(episodes_per_game=1, max_plies=24)
    assert len(results) == 4
    assert {result.game for result in results} == {"chess", "checkers"}
    assert {result.opponent for result in results} == {"random", "greedy"}
    assert network.output_weights != before


def test_invalid_feedback_name_is_rejected():
    network = SparsePolicyNetwork()
    try:
        network.adjust_from_error("invented_error")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown feedback must be rejected")
