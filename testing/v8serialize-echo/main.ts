import v8 from "node:v8";
import http from "node:http";
import consumers from "node:stream/consumers";
import { inspect } from "node:util";

// Create a local server to receive data from
const server = http.createServer(async (req, res) => {
  const url = new URL(
    req.url ?? "/",
    `http://${req.headers.host ?? "localhost"}`,
  );
  console.log(`${req.method} ${req.url} ${JSON.stringify(req.headers)}`);
  if (url.pathname != "/") {
    res.statusCode = 404;
    return res.end("URL must be /\n");
  }

  if (req.method === "POST") {
    if (req.headers["content-type"] != "application/x-v8-serialized") {
      res.statusCode = 400;
      return res.end("Content-Type must be application/x-v8-serialized\n");
    }
    const body = await consumers.buffer(req);
    let object: unknown;
    try {
      object = v8.deserialize(body);
    } catch (e) {
      res.writeHead(400);
      return res.end(`Unable to deserialize V8-serialized data: ${e}\n`);
    }
    const interpretation = inspect(object, {
      depth: null,
      maxStringLength: null,
      maxArrayLength: null,
    });
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({
      interpretation,
      serialization: {
        encoding: "base64",
        data: v8.serialize(object).toString("base64"),
      },
    }));
  } else if (req.method === "GET") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    return res.end("POST v8-serialized data to /\n");
  } else {
    res.writeHead(405);
    res.end("Method not allowed\n");
  }
});

server.listen(8000);
