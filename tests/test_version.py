from klod import __version__

def test_api_package_version_is_current():
    assert __version__ == "0.4.0"
