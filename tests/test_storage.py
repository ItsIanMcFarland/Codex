from pathlib import Path

from hotel_social_discover.storage import ResultRow, read_input_csv, write_output_csv


def test_read_input_csv(tmp_path: Path):
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("hotel_id,hotel_name,url\n1,Test Hotel,https://example.com\n")
    rows = read_input_csv(csv_path)
    assert rows == [{"hotel_id": "1", "hotel_name": "Test Hotel", "url": "https://example.com"}]


def test_write_output_csv(tmp_path: Path):
    output_path = tmp_path / "out.csv"
    row = ResultRow(hotel_id="1", hotel_name="Test Hotel", url="https://example.com")
    write_output_csv(output_path, [row])
    content = output_path.read_text().splitlines()
    assert content[0].startswith("hotel_id,hotel_name")
    assert "1" in content[1]
