import { Buffer } from "node:buffer";
import http from "node:http";
import { env } from "node:process";
import consumers from "node:stream/consumers";
import { inspect } from "node:util";
import v8 from "node:v8";

function parseSettings() {
  const logWithColor: boolean = env.V8SERIALIZE_LOG_WITH_COLOR === "true";
  const logListen: boolean = env.V8SERIALIZE_LOG_LISTEN !== "false";
  const logReserializationMode = /^(json|text|none)$/i.exec(
    env.V8SERIALIZE_LOG_RE_SERIALIZATION || "text",
  )?.[0] as "json" | "text" | "none" | undefined;

  if (!logReserializationMode) {
    throw new Error(
      `V8SERIALIZE_LOG_RE_SERIALIZATION must be 'json', 'text' or 'none'`,
    );
  }

  const listenPort: number = Number.parseInt(env.V8SERIALIZE_PORT || "8000");
  if (isNaN(listenPort) || listenPort < 0) {
    throw new Error(`V8SERIALIZE_PORT is not a port number`);
  }
  const listenHostname: string = env.V8SERIALIZE_HOSTNAME || "localhost";

  return {
    log: {
      withColors: logWithColor,
      reserialization: logReserializationMode,
      listen: logListen,
    },
    listen: { hostname: listenHostname, port: listenPort },
  };
}

const settings = parseSettings();

function logReserialization(
  input: Buffer,
  result: ReSerializeResult,
) {
  const mode = settings.log.reserialization;
  if (mode === "none") return;

  const inputBase64 = input.toString("base64");

  if (result.success) {
    if (mode === "json") {
      console.log(JSON.stringify({
        success: true,
        input: input.toString("base64"),
        interpretation: result.interpretation,
      }));
    } else {
      console.log(`OK ${inputBase64} ⇒ ${result.interpretation}`);
    }
  } else if (!result.success) {
    if (mode === "json") {
      console.log(JSON.stringify({
        success: false,
        error: result.error.name,
        message: result.error.message,
        input: input.toString("base64"),
        interpretation: result.error.interpretation,
      }));
    } else {
      const prefix = `ERROR (${result.error.name}) ${inputBase64}`;
      if (result.error.name === "deserialize-failed") {
        console.log(`${prefix} — ${result.error.message}`);
      } else {
        console.log(
          `${prefix} ⇒ ${result.error.interpretation} — ${result.error.message}`,
        );
      }
    }
  }
}

type HttpResponse = http.ServerResponse<http.IncomingMessage> & {
  req: http.IncomingMessage;
};

async function handleRequest(
  req: http.IncomingMessage,
  res: HttpResponse,
): Promise<HttpResponse> {
  const url = new URL(
    req.url ?? "/",
    `http://${req.headers.host ?? "localhost"}`,
  );
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
    const result = reSerialize(body);

    logReserialization(body, result);

    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify(result));
  } else if (req.method === "GET") {
    res.writeHead(200, { "Content-Type": "text/plain" });
    return res.end("POST V8-serialized data to /\n");
  } else {
    res.writeHead(405);
    return res.end("Method not allowed\n");
  }
}

type ReSerializeResult =
  | {
    success: true;
    interpretation: string;
    serialization: { encoding: "base64"; data: string };
  }
  | {
    success: false;
    error: {
      name: "deserialize-failed";
      message: string;
      interpretation?: undefined;
    };
  }
  | {
    success: false;
    error: {
      name: "serialize-failed";
      message: string;
      interpretation: string;
    };
  };

function reSerialize(payload: Buffer): ReSerializeResult {
  let object: unknown;
  try {
    object = v8.deserialize(payload);
  } catch (e) {
    return {
      success: false,
      error: { name: "deserialize-failed", message: String(e) },
    };
  }
  const interpretation = inspect(object, {
    depth: 10,
    colors: settings.log.withColors,
  });
  let serializationBase64: string;
  try {
    serializationBase64 = v8.serialize(object).toString("base64");
  } catch (e) {
    return {
      success: false,
      error: { name: "serialize-failed", message: String(e), interpretation },
    };
  }

  return {
    success: true,
    interpretation,
    serialization: {
      encoding: "base64",
      data: serializationBase64,
    },
  };
}

const server = http.createServer(async (req, res) => {
  try {
    await handleRequest(req, res);
  } catch (e) {
    console.error(`Failed to handle request`, e);
    if (!res.headersSent) {
      res.writeHead(500, "Internal server error");
    }
    res.end();
  }
});

server.listen(settings.listen.port, settings.listen.hostname, () => {
  if (settings.log.listen) {
    console.error(`Listening on ${inspect(server.address())}`);
  }
});
