from gortguard.cli import main


def test_stub_runs(capsys):
    assert main([]) == 0
    assert "no commands yet" in capsys.readouterr().out
