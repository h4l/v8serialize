ECHOSERVER_VERSION = "0.1.0"
DNT_NODE_VERSION = "22"
DNT_DENO_VERSION = "1.46.1"

group "default" {
  targets = ["echoserver-deno", "echoserver-node"]
}

target "_base" {
  args = {
    DNT_NODE_VERSION = DNT_NODE_VERSION,
    DNT_DENO_VERSION = DNT_DENO_VERSION,
    ECHOSERVER_VERSION = ECHOSERVER_VERSION,
  }
}

target "echoserver-deno" {
  name = "echoserver-deno-${replace(version, ".", "-")}"
  matrix = {
    version = [ "1.46.1" ]
  }
  inherits = ["_base"]
  target = "echoserver-deno"
  args = {
    DENO_VERSION = "alpine-${version}",
  }
  tags = ["ghcr.io/h4l/v8serialize/echoserver:deno-${version}"]
}

target "echoserver-node" {
  name = "echoserver-node-${version}"
  matrix = {
    version = ["18", "22"]
  }
  inherits = ["_base"]
  target = "echoserver-node"
  args = {
    NODE_VERSION = "${version}-alpine",
  }
  tags = ["ghcr.io/h4l/v8serialize/echoserver:node-${version}"]
}
