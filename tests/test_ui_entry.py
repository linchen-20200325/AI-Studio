from see.ui.__main__ import main


def test_ui_entry_defaults_to_loopback(monkeypatch, capsys):
    captured = {}

    class FakeUvicorn:
        @staticmethod
        def run(app, host, port, log_level):
            captured.update(app=app, host=host, port=port)

    import sys
    monkeypatch.setitem(sys.modules, "uvicorn", FakeUvicorn)
    assert main([]) == 0
    assert captured["host"] == "127.0.0.1" and captured["port"] == 8000
    assert "⚠" not in capsys.readouterr().err
    assert main(["--lan", "--port", "8123"]) == 0
    assert captured["host"] == "0.0.0.0" and captured["port"] == 8123
    assert "可信任區網" in capsys.readouterr().err
