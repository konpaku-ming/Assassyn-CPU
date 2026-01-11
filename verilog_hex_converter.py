from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Iterable, List


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


def _format_lines(data: bytes, line_width: int) -> List[str]:
    if line_width <= 0:
        raise ValueError("line_width must be positive")

    padded = bytes(data)
    remainder = len(padded) % line_width
    if remainder:
        padded += bytes(line_width - remainder)

    lines = []
    for idx in range(0, len(padded), line_width):
        chunk = padded[idx : idx + line_width]
        lines.append("".join(f"{byte:02X}" for byte in chunk))
    return lines


def convert_verilog_hex(source: Path, dest: Path, line_width: int = 8) -> Path:
    data = parse_verilog_hex(source)
    lines = _format_lines(data, line_width)

    dest.parent.mkdir(parents=True, exist_ok=True)
    output = "\n".join(lines)
    if lines:
        output += "\n"
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
        default=8,
        help="Number of bytes per line in the output file.",
    )

    args = parser.parse_args()

    for input_path in args.inputs:
        output_dir = args.output_dir if args.output_dir else input_path.parent
        output_path = output_dir / (input_path.stem + ".hex")
        convert_verilog_hex(input_path, output_path, line_width=args.line_width)


if __name__ == "__main__":
    _main()
