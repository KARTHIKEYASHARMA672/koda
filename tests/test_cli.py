from __future__ import annotations

from koda.cli import build_parser


def test_cli_parser_supports_doctor_serve_ask_and_island() -> None:
    parser = build_parser()

    assert parser.parse_args(["doctor"]).command == "doctor"
    assert parser.parse_args(["serve", "--port", "8765"]).port == 8765
    assert parser.parse_args(["ask", "hello", "koda"]).prompt == ["hello", "koda"]
    assert parser.parse_args(["island"]).command == "island"
