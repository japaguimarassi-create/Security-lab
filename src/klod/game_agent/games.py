from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


PIECE_VALUES = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0}


class GameAdapter(Protocol):
    game_id: str

    def initial_state(self): ...
    def legal_actions(self, state) -> list: ...
    def apply(self, state, action): ...
    def terminal(self, state) -> bool: ...
    def winner(self, state) -> int | None: ...
    def features(self, state, action) -> tuple[float, ...]: ...
    def action_label(self, action) -> str: ...
    def state_key(self, state): ...


@dataclass(frozen=True)
class ChessMove:
    source: int
    target: int
    promotion: str = ""
    flag: str = ""

    def uci(self) -> str:
        return square_name(self.source) + square_name(self.target) + self.promotion.lower()


@dataclass(frozen=True)
class ChessState:
    board: tuple[str, ...]
    turn: int = 1
    castling: str = "KQkq"
    ep: int = -1
    halfmove: int = 0
    fullmove: int = 1


def square_name(index: int) -> str:
    return chr(ord("a") + (index & 7)) + str(8 - (index >> 4))


def parse_square(value: str) -> int:
    if len(value) != 2 or value[0] not in "abcdefgh" or value[1] not in "12345678":
        raise ValueError(f"invalid square: {value}")
    return (8 - int(value[1])) * 16 + ord(value[0]) - ord("a")


def _on(index: int) -> bool:
    return 0 <= index < 128 and (index & 0x88) == 0


def _side(piece: str) -> int:
    if not piece:
        return 0
    return 1 if piece.isupper() else -1


class ChessGame:
    game_id = "chess"
    _knight = (-33, -31, -18, -14, 14, 18, 31, 33)
    _king = (-17, -16, -15, -1, 1, 15, 16, 17)
    _bishop = (-17, -15, 15, 17)
    _rook = (-16, -1, 1, 16)

    def initial_state(self) -> ChessState:
        rows = ("rnbqkbnr", "pppppppp", "........", "........", "........", "........", "PPPPPPPP", "RNBQKBNR")
        board = ["" for _ in range(128)]
        for row, text in enumerate(rows):
            for col, piece in enumerate(text):
                board[row * 16 + col] = "" if piece == "." else piece
        return ChessState(tuple(board))

    def _attacked(self, state: ChessState, target: int, by: int) -> bool:
        b = state.board
        for source in range(128):
            if not _on(source) or _side(b[source]) != by:
                continue
            piece = b[source].lower()
            if piece == "p":
                direction = -16 if by == 1 else 16
                if target in (source + direction - 1, source + direction + 1):
                    return True
                continue
            directions = self._knight if piece == "n" else self._king if piece == "k" else self._bishop if piece == "b" else self._rook if piece == "r" else self._bishop + self._rook
            for delta in directions:
                step = source + delta
                while _on(step):
                    if step == target:
                        return True
                    if b[step]:
                        break
                    if piece in ("n", "k"):
                        break
                    step += delta
        return False

    def in_check(self, state: ChessState, color: int | None = None) -> bool:
        side = state.turn if color is None else color
        king = "K" if side == 1 else "k"
        try:
            square = state.board.index(king)
        except ValueError:
            return True
        return self._attacked(state, square, -side)

    def _pseudo(self, state: ChessState) -> list[ChessMove]:
        b, turn = state.board, state.turn
        moves: list[ChessMove] = []

        def add(source: int, target: int, flag: str = "") -> None:
            if b[target].lower() == "k":
                return
            row = target >> 4
            if b[source].lower() == "p" and row in (0, 7):
                for promotion in ("q", "r", "b", "n"):
                    moves.append(ChessMove(source, target, promotion, flag))
            else:
                moves.append(ChessMove(source, target, "", flag))

        for source in range(128):
            if not _on(source) or _side(b[source]) != turn:
                continue
            piece = b[source].lower()
            if piece == "p":
                forward = -16 * turn
                one = source + forward
                if _on(one) and not b[one]:
                    add(source, one)
                    two = one + forward
                    home_row = 6 if turn == 1 else 1
                    if source >> 4 == home_row and _on(two) and not b[two]:
                        add(source, two)
                for diagonal in (-1, 1):
                    target = one + diagonal
                    if not _on(target):
                        continue
                    if _side(b[target]) == -turn:
                        add(source, target)
                    elif target == state.ep and not b[target]:
                        add(source, target, "ep")
                continue
            directions = self._knight if piece == "n" else self._king if piece == "k" else self._bishop if piece == "b" else self._rook if piece == "r" else self._bishop + self._rook
            for delta in directions:
                target = source + delta
                while _on(target) and _side(b[target]) != turn:
                    add(source, target)
                    if b[target] or piece in ("n", "k"):
                        break
                    target += delta
            if piece == "k":
                home = 116 if turn == 1 else 4
                rights = ("K", "Q") if turn == 1 else ("k", "q")
                rook = "R" if turn == 1 else "r"
                if source == home and not self.in_check(state, turn):
                    if rights[0] in state.castling and b[home + 3] == rook and not b[home + 1] and not b[home + 2]:
                        if not self._attacked(state, home + 1, -turn) and not self._attacked(state, home + 2, -turn):
                            add(source, home + 2, "castle")
                    if rights[1] in state.castling and b[home - 4] == rook and not b[home - 1] and not b[home - 2] and not b[home - 3]:
                        if not self._attacked(state, home - 1, -turn) and not self._attacked(state, home - 2, -turn):
                            add(source, home - 2, "castle")
        return moves

    def apply(self, state: ChessState, move: ChessMove) -> ChessState:
        if move not in self.legal_actions(state):
            raise ValueError("illegal chess move")
        b = list(state.board)
        piece = b[move.source]
        captured = b[move.target]
        b[move.source] = ""
        b[move.target] = move.promotion.upper() if piece.isupper() and move.promotion else move.promotion.lower() if move.promotion else piece
        if move.flag == "ep":
            b[move.target + 16 * state.turn] = ""
        if move.flag == "castle":
            rook_from = move.source + (3 if move.target > move.source else -4)
            rook_to = move.source + (1 if move.target > move.source else -1)
            b[rook_to], b[rook_from] = b[rook_from], ""
        rights = state.castling
        if piece == "K":
            rights = rights.replace("K", "").replace("Q", "")
        elif piece == "k":
            rights = rights.replace("k", "").replace("q", "")
        rook_rights = {119: "K", 112: "Q", 7: "k", 0: "q"}
        if piece.lower() == "r":
            rights = rights.replace(rook_rights.get(move.source, "!"), "")
        if captured.lower() == "r":
            rights = rights.replace(rook_rights.get(move.target, "!"), "")
        ep = (move.source + move.target) // 2 if piece.lower() == "p" and abs(move.target - move.source) == 32 else -1
        halfmove = 0 if piece.lower() == "p" or captured or move.flag == "ep" else state.halfmove + 1
        fullmove = state.fullmove + (1 if state.turn == -1 else 0)
        return ChessState(tuple(b), -state.turn, rights, ep, halfmove, fullmove)

    def legal_actions(self, state: ChessState) -> list[ChessMove]:
        legal = []
        for move in self._pseudo(state):
            next_state = self._apply_unchecked(state, move)
            if not self.in_check(next_state, state.turn):
                legal.append(move)
        return legal

    def _apply_unchecked(self, state: ChessState, move: ChessMove) -> ChessState:
        b = list(state.board)
        piece = b[move.source]
        captured = b[move.target]
        b[move.source] = ""
        b[move.target] = move.promotion.upper() if piece.isupper() and move.promotion else move.promotion.lower() if move.promotion else piece
        if move.flag == "ep":
            b[move.target + 16 * state.turn] = ""
        if move.flag == "castle":
            rook_from = move.source + (3 if move.target > move.source else -4)
            rook_to = move.source + (1 if move.target > move.source else -1)
            b[rook_to], b[rook_from] = b[rook_from], ""
        rights = state.castling
        if piece == "K":
            rights = rights.replace("K", "").replace("Q", "")
        elif piece == "k":
            rights = rights.replace("k", "").replace("q", "")
        rook_rights = {119: "K", 112: "Q", 7: "k", 0: "q"}
        if piece.lower() == "r":
            rights = rights.replace(rook_rights.get(move.source, "!"), "")
        if captured.lower() == "r":
            rights = rights.replace(rook_rights.get(move.target, "!"), "")
        ep = (move.source + move.target) // 2 if piece.lower() == "p" and abs(move.target - move.source) == 32 else -1
        halfmove = 0 if piece.lower() == "p" or captured or move.flag == "ep" else state.halfmove + 1
        fullmove = state.fullmove + (1 if state.turn == -1 else 0)
        return ChessState(tuple(b), -state.turn, rights, ep, halfmove, fullmove)

    def terminal(self, state: ChessState) -> bool:
        return not self.legal_actions(state) or state.halfmove >= 100

    def winner(self, state: ChessState) -> int | None:
        if state.halfmove >= 100:
            return None
        if self.legal_actions(state):
            return None
        return -state.turn if self.in_check(state, state.turn) else None

    def state_key(self, state: ChessState) -> tuple:
        return state.board, state.turn, state.castling, state.ep

    def features(self, state: ChessState, move: ChessMove, history: set[tuple] | None = None) -> tuple[float, ...]:
        board = state.board
        piece = board[move.source]
        capture = board[move.target]
        if move.flag == "ep":
            capture = "p" if state.turn == 1 else "P"
        next_state = self._apply_unchecked(state, move)
        moved_piece = next_state.board[move.target]
        opponent = -state.turn
        exposed = 1.0 if self._attacked(next_state, move.target, opponent) else 0.0
        protected = 1.0 if self._attacked(next_state, move.target, state.turn) else 0.0
        source_center = 1.0 if (move.source & 7, move.source >> 4) in ((3, 3), (4, 3), (3, 4), (4, 4)) else 0.0
        target_center = 1.0 if (move.target & 7, move.target >> 4) in ((3, 3), (4, 3), (3, 4), (4, 4)) else 0.0
        advancement = ((move.source >> 4) - (move.target >> 4)) * state.turn / 7.0
        capture_value = PIECE_VALUES.get(capture.lower(), 0) / 9.0
        material_gain = (PIECE_VALUES.get(capture.lower(), 0) + (PIECE_VALUES.get(move.promotion, 0) if move.promotion else 0)) / 9.0
        return (
            capture_value,
            PIECE_VALUES.get(piece.lower(), 0) / 9.0,
            1.0 if move.promotion else 0.0,
            target_center - source_center,
            max(-1.0, min(1.0, advancement)),
            exposed,
            1.0 if self.in_check(next_state, opponent) else 0.0,
            1.0 if move.flag == "castle" else 0.0,
            protected,
            0.0,
            0.0,
            1.0 if history is not None and self.state_key(next_state) in history else 0.0,
            material_gain,
            0.0,
            1.0 if moved_piece.lower() == "k" else 0.0,
            0.05,
        )

    def action_label(self, action: ChessMove) -> str:
        return action.uci()


@dataclass(frozen=True)
class DraughtsMove:
    path: tuple[int, ...]

    @property
    def captures(self) -> int:
        return sum(1 for first, last in zip(self.path, self.path[1:]) if abs(first // 8 - last // 8) == 2)

    def label(self) -> str:
        return "x".join(str(square + 1) for square in self.path) if self.captures else "-".join(str(square + 1) for square in self.path)


@dataclass(frozen=True)
class DraughtsState:
    board: tuple[int, ...]
    turn: int = 1
    ply: int = 0
    quiet_plies: int = 0


class DraughtsGame:
    game_id = "checkers"

    def initial_state(self) -> DraughtsState:
        board = [0] * 64
        for row in range(3):
            for col in range(8):
                if (row + col) % 2 == 1:
                    board[row * 8 + col] = -1
        for row in range(5, 8):
            for col in range(8):
                if (row + col) % 2 == 1:
                    board[row * 8 + col] = 1
        return DraughtsState(tuple(board))

    def _directions(self, piece: int) -> tuple[tuple[int, int], ...]:
        if abs(piece) == 2:
            return ((-1, -1), (-1, 1), (1, -1), (1, 1))
        forward = -1 if piece > 0 else 1
        return ((forward, -1), (forward, 1))

    def _captures_from(self, board: tuple[int, ...], source: int) -> list[DraughtsMove]:
        piece = board[source]
        row, col = divmod(source, 8)
        found: list[DraughtsMove] = []
        for dr, dc in self._directions(piece):
            mr, mc = row + dr, col + dc
            tr, tc = row + 2 * dr, col + 2 * dc
            if not (0 <= tr < 8 and 0 <= tc < 8 and 0 <= mr < 8 and 0 <= mc < 8):
                continue
            middle, target = mr * 8 + mc, tr * 8 + tc
            if board[middle] * piece < 0 and board[target] == 0:
                updated = list(board)
                updated[source] = 0
                updated[middle] = 0
                promoted = abs(piece) == 1 and ((piece > 0 and tr == 0) or (piece < 0 and tr == 7))
                updated[target] = piece * 2 if promoted else piece
                if promoted:
                    found.append(DraughtsMove((source, target)))
                    continue
                continuations = self._captures_from(tuple(updated), target)
                if continuations:
                    found.extend(DraughtsMove((source,) + move.path) for move in continuations)
                else:
                    found.append(DraughtsMove((source, target)))
        return found

    def legal_actions(self, state: DraughtsState) -> list[DraughtsMove]:
        captures: list[DraughtsMove] = []
        quiet: list[DraughtsMove] = []
        for source, piece in enumerate(state.board):
            if piece * state.turn <= 0:
                continue
            captures.extend(self._captures_from(state.board, source))
            row, col = divmod(source, 8)
            for dr, dc in self._directions(piece):
                tr, tc = row + dr, col + dc
                if 0 <= tr < 8 and 0 <= tc < 8 and state.board[tr * 8 + tc] == 0:
                    quiet.append(DraughtsMove((source, tr * 8 + tc)))
        return captures if captures else quiet

    def apply(self, state: DraughtsState, move: DraughtsMove) -> DraughtsState:
        legal = self.legal_actions(state)
        if move not in legal:
            raise ValueError("illegal checkers move")
        board = list(state.board)
        source, target = move.path[0], move.path[-1]
        piece = board[source]
        board[source] = 0
        for first, last in zip(move.path, move.path[1:]):
            if abs((first // 8) - (last // 8)) == 2:
                middle = ((first // 8 + last // 8) // 2) * 8 + ((first % 8 + last % 8) // 2)
                board[middle] = 0
        row = target // 8
        promoted = abs(piece) == 1 and ((piece > 0 and row == 0) or (piece < 0 and row == 7))
        board[target] = piece * 2 if promoted else piece
        captured = move.captures
        return DraughtsState(tuple(board), -state.turn, state.ply + 1, 0 if captured or promoted else state.quiet_plies + 1)

    def terminal(self, state: DraughtsState) -> bool:
        if not any(piece * state.turn > 0 for piece in state.board):
            return True
        return not self.legal_actions(state) or state.quiet_plies >= 80

    def winner(self, state: DraughtsState) -> int | None:
        if state.quiet_plies >= 80:
            return None
        if any(self.legal_actions(state)):
            return None
        return -state.turn if any(piece * -state.turn > 0 for piece in state.board) else None

    def state_key(self, state: DraughtsState) -> tuple:
        return state.board, state.turn

    def features(self, state: DraughtsState, move: DraughtsMove, history: set[tuple] | None = None) -> tuple[float, ...]:
        board = state.board
        source, target = move.path[0], move.path[-1]
        piece = board[source]
        row0, col0 = divmod(source, 8)
        row1, col1 = divmod(target, 8)
        captures = move.captures
        promoted = abs(piece) == 1 and ((piece > 0 and row1 == 0) or (piece < 0 and row1 == 7))
        center0 = 1.0 if 2 <= col0 <= 5 and 2 <= row0 <= 5 else 0.0
        center1 = 1.0 if 2 <= col1 <= 5 and 2 <= row1 <= 5 else 0.0
        advancement = ((row0 - row1) * state.turn) / 7.0
        next_state = self.apply(state, move)
        exposed = 0.0
        for enemy_move in self.legal_actions(next_state):
            if enemy_move.captures and enemy_move.path[-1] == target:
                exposed = 1.0
                break
        friends_near = 0
        for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            rr, cc = row1 + dr, col1 + dc
            if 0 <= rr < 8 and 0 <= cc < 8 and next_state.board[rr * 8 + cc] * state.turn > 0:
                friends_near += 1
        return (
            min(1.0, captures / 3.0),
            abs(piece) / 2.0,
            1.0 if promoted else 0.0,
            center1 - center0,
            max(-1.0, min(1.0, advancement)),
            exposed,
            0.0,
            0.0,
            min(1.0, friends_near / 3.0),
            0.0,
            0.0,
            1.0 if history is not None and self.state_key(next_state) in history else 0.0,
            min(1.0, captures / 3.0 + (1.0 if promoted else 0.0)),
            1.0 if captures > 1 else 0.0,
            1.0 if abs(piece) == 2 else 0.0,
            0.04,
        )

    def action_label(self, action: DraughtsMove) -> str:
        return action.label()
