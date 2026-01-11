from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Iterable
from pathlib import Path
from string import hexdigits


def _iter_tokens(source: Path) -> Iterable[str]:
    content = source.read_text()
    for token in content.split():
        cleaned = token.strip()
        if cleaned:
            yield cleaned


def parse_verilog_hex(source: Path) -> bytearray:
    """
    Parse a Verilog-style hex/mem file that may contain address directives.

    Supported format:
    - Data bytes are written as two-digit hex values.
    - Address changes are specified with tokens starting with '@'.
    """
    memory = {}
    current_address = 0
    max_address = -1

    for token in _iter_tokens(source):
        if token.startswith("@"):
            try:
                current_address = int(token[1:], 16)
            except ValueError as exc:
                raise ValueError(f"Invalid address token: {token}") from exc
            continue

        try:
            byte_value = int(token, 16) & 0xFF
        except ValueError as exc:
            raise ValueError(f"Invalid byte token: {token}") from exc

        memory[current_address] = byte_value
        max_address = max(max_address, current_address)
        current_address += 1

    if max_address < 0:
        return bytearray()

    buffer = bytearray(max_address + 1)
    for addr, value in memory.items():
        buffer[addr] = value
    return buffer


def _format_lines(data: bytes, line_width: int) -> list[str]:
    if line_width <= 0:
        raise ValueError("line_width must be positive")

    data_bytes = bytes(data)
    remainder = len(data_bytes) % line_width
    padded_data = (
        data_bytes if remainder == 0 else data_bytes + bytes(line_width - remainder)
    )

    lines = []
    for idx in range(0, len(padded_data), line_width):
        chunk = padded_data[idx : idx + line_width]
        word_value = int.from_bytes(chunk, byteorder="little")
        lines.append(f"{word_value:0{line_width * 2}X}")
    return lines


def _parse_dump_words(dump_path: Path, line_width: int) -> dict[int, int]:
    words: dict[int, int] = {}
    for line in dump_path.read_text().splitlines():
        if ":" not in line:
            continue
        addr_part, remainder = line.split(":", 1)
        try:
            address = int(addr_part.strip(), 16)
        except ValueError:
            continue

        tokens = remainder.strip().split()
        if not tokens:
            continue
        word_token = tokens[0]
        if (
            len(word_token) == line_width * 2
            and all(ch in hexdigits for ch in word_token)
        ):
            words[address] = int(word_token, 16)
    return words


def _validate_against_dump(
    lines: list[str], dump_words: dict[int, int], line_width: int
) -> None:
    for address, expected in dump_words.items():
        if address % line_width != 0:
            continue
        line_idx = address // line_width
        if line_idx >= len(lines):
            raise ValueError(
                f"Dump expects address 0x{address:X}, but converted data ends earlier."
            )
        actual = int(lines[line_idx], 16)
        if actual != expected:
            raise ValueError(
                f"Dump mismatch at 0x{address:X}: expected {expected:0{line_width * 2}X}, "
                f"got {actual:0{line_width * 2}X}"
            )


def convert_verilog_hex(
    source: Path, dest: Path, line_width: int = 4, dump_path: Path | None = None
) -> Path:
    data = parse_verilog_hex(source)
    lines = _format_lines(data, line_width)

    if dump_path and dump_path.exists():
        dump_words = _parse_dump_words(dump_path, line_width)
        if dump_words:
            _validate_against_dump(lines, dump_words, line_width)

    dest.parent.mkdir(parents=True, exist_ok=True)
    output = "\n".join(lines) + "\n" if lines else ""
    dest.write_text(output)
    return dest


def _main() -> None:
    parser = ArgumentParser(description="Convert Verilog hex files to packed hex format.")
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input Verilog hex file(s).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated files (default: alongside each input file).",
    )
    parser.add_argument(
        "--line-width",
        type=int,
        default=4,
        help="Number of bytes per line in the output file.",
    )
    parser.add_argument(
        "--dump",
        type=Path,
        default=None,
        help="Optional dump file to validate converted output (defaults to sibling .dump if present).",
    )

    args = parser.parse_args()

    for input_path in args.inputs:
        output_dir = args.output_dir if args.output_dir else input_path.parent
        output_path = output_dir / (input_path.stem + ".hex")
        dump_path = args.dump
        if dump_path is None:
            candidate = input_path.with_suffix(".dump")
            dump_path = candidate if candidate.exists() else None

        convert_verilog_hex(
            input_path, output_path, line_width=args.line_width, dump_path=dump_path
        )


if __name__ == "__main__":
    _main()
