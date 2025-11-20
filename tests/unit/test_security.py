import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from aigent.core.tools import validate_path, fs_read, fs_write

@pytest.fixture
def mock_profile_manager():
    with patch("aigent.core.tools.ProfileManager") as MockPM:
        pm_instance = MockPM.return_value
        # Default to allow only current directory
        pm_instance.config.allowed_work_dirs = ["."]
        yield pm_instance

def test_path_validation_success(tmp_path, mock_profile_manager):
    # Override allowed dirs to tmp_path for this test
    mock_profile_manager.config.allowed_work_dirs = [str(tmp_path)]
    
    allowed_file = tmp_path / "safe.txt"
    allowed_file.touch()
    
    # Should pass
    assert validate_path(allowed_file) is None
    
    # Subdir should pass
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    subfile = subdir / "nested.txt"
    assert validate_path(subfile) is None

def test_path_validation_failure(tmp_path, mock_profile_manager):
    # Override allowed dirs to tmp_path
    mock_profile_manager.config.allowed_work_dirs = [str(tmp_path)]
    
    # Access /etc/passwd
    forbidden = Path("/etc/passwd")
    error = validate_path(forbidden)
    assert error is not None
    assert "Access Denied" in error
    
    # Access parent of tmp_path
    parent = tmp_path.parent / "outside.txt"
    error = validate_path(parent)
    assert error is not None
    assert "Access Denied" in error

def test_fs_read_security(tmp_path, mock_profile_manager):
    mock_profile_manager.config.allowed_work_dirs = [str(tmp_path)]
    
    # Safe
    f = tmp_path / "ok.txt"
    f.write_text("ok")
    assert fs_read(str(f)) == "ok"
    
    # Unsafe
    assert "Access Denied" in fs_read("/etc/passwd")
