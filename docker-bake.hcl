group "default" {
    targets = ["test", "test_package", "lint"]
}

// TODO: integration

function "python_image_tag" {
  params = [version]
  result = version == "latest" ? "slim" : "${version}-slim"
}

function "version_name" {
  params = [version]
  result = replace(version, ".", "")
}

py_versions = ["3.10", "3.11", "3.12", "3.13"]

target "test" {
    name = "test_py${version_name(py_version)}"
    matrix = {
        py_version = py_versions,
    }
    args = {
        PYTHON_VER = python_image_tag(py_version)
    }
    target = "test"
    no-cache-filter = ["test"]
    output = ["type=cacheonly"]
}

target "test_package" {
    name = "test_package_py${version_name(py_version)}"
    matrix = {
        py_version = py_versions,
    }
    args = {
        PYTHON_VER = python_image_tag(py_version)
    }
    target = "test-package"
    no-cache-filter = ["test-package"]
    output = ["type=cacheonly"]
}

target "lint" {
    name = "lint-${lint_type}"
    matrix = {
        lint_type = ["check", "format", "mypy"],
    }
    args = {
        PYTHON_VER = "slim"
    }
    target = "lint-${lint_type}"
    no-cache-filter = ["lint-setup"]
    output = ["type=cacheonly"]
}

target "dev" {
    name = "dev_py${version_name(py_version)}"
    matrix = {
        py_version = py_versions,
    }
    inherits = ["test_py${version_name(py_version)}"]
    no-cache-filter = []
    output = []
    target = "poetry"
    tags = ["v8serialize-dev:py${version_name(py_version)}"]
}
