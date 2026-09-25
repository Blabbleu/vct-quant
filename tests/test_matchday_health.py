"""The matchday gate must check upstream-backed endpoints, not only the API root."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("failed_endpoint", ["events", "upcoming"])
def test_matchday_skips_update_when_source_endpoint_is_down(tmp_path, failed_endpoint):
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    shutil.copyfile(Path("scripts/matchday.sh"), root / "scripts" / "matchday.sh")
    shutil.copyfile(Path("scripts/check_vlrgg_feed.py"), root / "scripts" / "check_vlrgg_feed.py")
    (root / ".venv" / "bin" / "activate").write_text("")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for name, body in {
        "curl": ("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\n"
                 "case \"$*\" in\n"
                 f"  *'/v2/{'events' if failed_endpoint == 'events' else 'match?q=upcoming'}'*) exit 22;;\n"
                 "  *'/v2/'*) printf '%s\\n' '{\"status\":\"success\",\"data\":{\"status\":200,\"segments\":[]}}';;\n"
                 "esac\nexit 0\n"),
        "vct": "#!/bin/sh\nprintf 'vct %s\\n' \"$*\" >> \"$CALLS\"\nexit 0\n",
    }.items():
        path = bin_dir / name
        path.write_text(body)
        path.chmod(0o755)
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}", "CALLS": str(calls),
                        "VCT_MATCHDAY_UNTIL": "2099-12-31"}
    result = subprocess.run(["/bin/bash", str(root / "scripts" / "matchday.sh")],
                            cwd=tmp_path, env=env, timeout=5, check=False)
    log = (root / "data" / "interim" / "matchday.log").read_text()
    assert result.returncode == 1
    assert f"{failed_endpoint} feed unavailable" in log
    assert "vct update" not in calls.read_text()
    assert "python scripts/grade_predictions.py" not in calls.read_text()


def test_matchday_skips_http_200_error_envelope_before_any_write(tmp_path):
    """The root and HTTP status can be healthy while the upstream payload fails."""
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    (root / ".venv" / "bin").mkdir(parents=True)
    shutil.copyfile(Path("scripts/matchday.sh"), root / "scripts" / "matchday.sh")
    shutil.copyfile(Path("scripts/check_vlrgg_feed.py"), root / "scripts" / "check_vlrgg_feed.py")
    (root / ".venv" / "bin" / "activate").write_text("")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALLS\"\n"
                    "case \"$*\" in\n"
                    "  *'/v2/events?page=1'*) printf '%s\\n' '{\"status\":\"error\",\"data\":{\"segments\":[]}}';;\n"
                    "  *'/v2/match?q=upcoming'*) printf '%s\\n' '{\"status\":\"success\",\"data\":{\"status\":200,\"segments\":[]}}';;\n"
                    "esac\n")
    curl.chmod(0o755)
    vct = bin_dir / "vct"
    vct.write_text("#!/bin/sh\nprintf 'vct %s\\n' \"$*\" >> \"$CALLS\"\n")
    vct.chmod(0o755)
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}", "CALLS": str(calls),
                        "VCT_MATCHDAY_UNTIL": "2099-12-31"}
    result = subprocess.run(["/bin/bash", str(root / "scripts" / "matchday.sh")],
                            cwd=tmp_path, env=env, timeout=5, check=False)
    log = (root / "data" / "interim" / "matchday.log").read_text()
    assert result.returncode == 1
    assert "events feed unavailable" in log
    assert "vct update" not in calls.read_text()
