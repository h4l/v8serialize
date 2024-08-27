import { toArrayBuffer } from "@std/streams/to-array-buffer";
import { encodeBase64 } from "jsr:@std/encoding/base64";

import v8 from "node:v8";
// import { inspect } from "node:util";

Deno.serve({}, async (req, info) => {
  const url = new URL(req.url);

  // console.log(`${req.method} ${req.url} ${JSON.stringify(req.headers)}`);
  if (url.pathname != "/") {
    return new Response("URL must be /\n", { status: 404 });
  }

  if (req.method === "POST") {
    if (req.headers.get("content-type") != "application/x-v8-serialized") {
      return new Response(
        "Content-Type must be application/x-v8-serialized\n",
        { status: 400 },
      );
    }
    if (!req.body) {
      return new Response(
        "Request body is empty\n",
        { status: 400 },
      );
    }

    const body = await toArrayBuffer(req.body);
    let object: unknown;
    try {
      object = v8.deserialize(new Uint8Array(body));
    } catch (e) {
      // Return a 200 response because use of the API is correct, even though
      // the data is invalid.
      return new Response(
        JSON.stringify({
          success: false,
          message: `Unable to deserialize V8-serialized data: ${e}`,
        }),
        { headers: { "content-type": "application/json" } },
      );
    }

    const interpretation = Deno.inspect(object, { depth: 10 });
    const serializationBase64 = v8.serialize(object).toString("base64");
    console.log(
      `req: ${
        encodeBase64(body)
      }, interpretation: ${interpretation}, resp: ${serializationBase64}`,
    );
    return new Response(
      JSON.stringify({
        success: true,
        interpretation,
        serialization: {
          encoding: "base64",
          data: serializationBase64,
        },
      }),
      { headers: { "content-type": "application/json" } },
    );
  } else if (req.method === "GET") {
    return new Response("POST V8-serialized data to /\n", { status: 200 });
  } else {
    return new Response("Method not allowed\n", { status: 405 });
  }
});
