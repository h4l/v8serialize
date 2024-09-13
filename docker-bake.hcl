group "default" {
    targets = ["test", "lint"]
}

// TODO: integration

target "test" {
    name = "test_py${replace(py, ".", "")}"
    matrix = {
        py = ["3.9", "3.10", "3.11", "3.12", "3.13-rc"],
    }
    args = {
        PYTHON_VER = py == "latest" ? "slim" : "${py}-slim"
    }
    target = "test"
    no-cache-filter = ["test"]
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
