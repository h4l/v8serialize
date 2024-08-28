// ex. scripts/build_npm.ts
import { build, emptyDir } from "@deno/dnt";

await emptyDir("./npm");

await build({
  entryPoints: ["./main.ts"],
  outDir: "./npm",
  shims: {
    // see JS docs for overview and more options
    deno: true,
  },
  package: {
    // package.json properties
    name: "v8serialize-echoserver",
    version: Deno.args[0],
    description:
      "A simple HTTP server that deserializes a V8-serialized payload and reserializes it in the response.",
    license: "MIT",
    repository: {
      type: "git",
      url: "git+https://github.com/h4l/v8serialize.git",
    },
    bugs: {
      url: "https://github.com/h4l/v8serialize/issues",
    },
  },
  postBuild() {
    // steps to run after building and before running the tests
  },
});
