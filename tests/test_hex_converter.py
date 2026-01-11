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
        "0000BBAA",
        "00000000",
        "00000000",
        "00000000",
        "000000CC",
    ]


def test_convert_verilog_hex_uses_dump_for_validation(tmp_path: Path) -> None:
    source = tmp_path / "input.data"
    source.write_text(
        "\n".join(
            [
                "@00000000",
                "37 01 02 00 EF 10 00 04",
                "@00000008",
                "13 05 F0 0F",
            ]
        )
        + "\n"
    )

    dump = tmp_path / "input.dump"
    dump.write_text(
        "\n".join(
            [
                "00000000 <.text>:",
                "   0:   00020137           lui sp,0x20",
                "   4:   040010EF           jal ra,1044 <main>",
                "00000008 <.text+0x8>:",
                "   8:   0FF00513           li a0,255",
            ]
        )
        + "\n"
    )

    output = tmp_path / "out.hex"
    convert_verilog_hex(source, output, dump_path=dump)

    assert output.read_text().splitlines() == [
        "00020137",
        "040010EF",
        "0FF00513",
    ]
