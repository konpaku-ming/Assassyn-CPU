from pathlib import Path

from verilog_hex_converter import convert_verilog_hex


def test_convert_verilog_hex_handles_address_gaps(tmp_path: Path) -> None:
    source = tmp_path / "input.data"
    source.write_text(
        "\n".join(
            [
                "@00000000",
                "AA BB",
                "@00000010",
                "CC",
            ]
        )
        + "\n"
    )

    output = tmp_path / "out.hex"
    convert_verilog_hex(source, output)

    assert output.read_text().splitlines() == [
        "AABB000000000000",
        "0000000000000000",
        "CC00000000000000",
    ]
