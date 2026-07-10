import json
import os
import tempfile
import urllib.request
import urllib.error
import uuid


def _http_json(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_multipart(url: str, fields: dict[str, str], file_field: str, file_path: str, filename: str, content_type: str):
    boundary = "----contextengine-" + uuid.uuid4().hex
    crlf = "\r\n"

    body = bytearray()
    for k, v in fields.items():
        body.extend(f"--{boundary}{crlf}".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"{crlf}{crlf}'.encode("utf-8"))
        body.extend(str(v).encode("utf-8"))
        body.extend(crlf.encode("utf-8"))

    body.extend(f"--{boundary}{crlf}".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"{crlf}'.encode("utf-8")
    )
    body.extend(f"Content-Type: {content_type}{crlf}{crlf}".encode("utf-8"))
    with open(file_path, "rb") as f:
        body.extend(f.read())
    body.extend(crlf.encode("utf-8"))

    body.extend(f"--{boundary}--{crlf}".encode("utf-8"))

    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    base = os.environ.get("CONTEXT_ENGINE_API") or os.environ.get("ADVANCED_RAG_API", "http://127.0.0.1:8000")
    spaces = _http_json(f"{base}/api/knowledge-spaces")
    items = spaces.get("knowledge_spaces", [])
    test_space = next((s for s in items if s.get("name") == "TestSpace"), None)
    if not test_space:
        raise SystemExit("TestSpace not found. Create it first.")

    sid = test_space["id"]
    fp = os.path.join(tempfile.gettempdir(), "boot-kb.txt")
    with open(fp, "w", encoding="utf-8") as f:
        f.write("hello context-engine\n")

    status, text = _post_multipart(
        f"{base}/api/documents/upload",
        fields={"knowledge_space_id": sid},
        file_field="file",
        file_path=fp,
        filename="boot-kb.txt",
        content_type="text/plain",
    )
    print("upload_status", status)
    print(text)


if __name__ == "__main__":
    main()

