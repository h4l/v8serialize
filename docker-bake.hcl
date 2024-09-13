group "default" {
    targets = ["test", "lint"]
}

// TODO: integration

py_versions = ["3.9", "3.10", "3.11", "3.12", "3.13-rc"]

target "test" {
    name = "test_py${replace(py, ".", "")}"
    matrix = {
        py = py_versions,
    }
    args = {
        PYTHON_VER = py == "latest" ? "slim" : "${py}-slim"
    }
    target = "test"
    no-cache-filter = ["test"]
    output = ["type=cacheonly"]
}

target "test_package" {
  name = "test_package_py${replace(py, ".", "")}"
    matrix = {
        py = py_versions,
    }
    args = {
        PYTHON_VER = py == "latest" ? "slim" : "${py}-slim"
    }
    target = "test-package"
    no-cache-filter = ["test-package"]
    output = ["type=cacheonly"]
}

target "lint" {
    name = "lint-${lint_type}"
    matrix = {
        lint_type = ["flake8", "black", "isort", "mypy"],
    }
    args = {
        PYTHON_VER = "slim"
    }
    target = "lint-${lint_type}"
    no-cache-filter = ["lint-setup"]
    output = ["type=cacheonly"]
}
