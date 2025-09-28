import argparse

import asyncio

import cli


def test_crawl_handles_missing_proxy_file(tmp_path, monkeypatch, caplog):
    input_path = tmp_path / "hotels.csv"
    input_path.write_text("hotel_id,hotel_name,url\n")
    output_path = tmp_path / "results.csv"
    summary_path = tmp_path / "summary.json"
    checkpoint_path = tmp_path / "checkpoint.json"

    monkeypatch.setenv("HSD_CHECKPOINT_PATH", str(checkpoint_path))
    monkeypatch.setenv("HSD_SUMMARY_JSON", str(summary_path))

    args = argparse.Namespace(
        command="crawl",
        input=str(input_path),
        output=str(output_path),
        concurrency=None,
        timeout=None,
        headful=None,
        render=False,
        proxy_file=str(tmp_path / "proxies.txt"),
        resume="true",
        force=False,
        save_snapshots=False,
        summary_json=str(summary_path),
        log_file=None,
    )

    monkeypatch.setattr(cli, "configure_logging", lambda *_, **__: None)

    caplog.set_level("WARNING")

    asyncio.run(cli.crawl_command(args))

    assert output_path.exists(), "Output CSV should be created even when proxies are missing"
    assert summary_path.exists(), "Summary JSON should be written"
    assert checkpoint_path.exists(), "Checkpoint file should be saved"
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert any("Proxy file" in record.message for record in warnings), "Missing proxy file warning not logged"
