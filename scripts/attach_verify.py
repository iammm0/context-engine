import json
import os
import tempfile
import urllib.error
import urllib.request
import uuid


def http_json(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def post_multipart(url: str, fields: dict[str, str], file_path: str, filename: str, content_type: str) -> tuple[int, str]:
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
        f'Content-Disposition: form-data; name="file"; filename="{filename}"{crlf}'.encode("utf-8")
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
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    base = os.environ.get("CONTEXT_ENGINE_API") or os.environ.get("ADVANCED_RAG_API", "http://127.0.0.1:8000")

    conv = http_json(f"{base}/api/chat/conversations")
    conv_id = None
    if conv.get("conversations"):
        conv_id = conv["conversations"][0]["id"]
    if not conv_id:
        created = http_json(
            urllib.request.Request(
                f"{base}/api/chat/conversations",
                data=json.dumps({"title": "附件测试"}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            ).full_url
        )
        conv_id = created.get("id")

    spaces = http_json(f"{base}/api/knowledge-spaces")
    sid = next((s["id"] for s in spaces.get("knowledge_spaces", []) if s.get("name") == "TestSpace"), None)
    if not sid:
        sid = spaces["knowledge_spaces"][0]["id"]

    fp = os.path.join(tempfile.gettempdir(), "attach-test.txt")
    with open(fp, "w", encoding="utf-8") as f:
        f.write("attachment hello\n")

    status, text = post_multipart(
        f"{base}/api/chat/conversation-attachment",
        fields={"conversation_id": conv_id, "knowledge_space_id": sid},
        file_path=fp,
        filename="attach-test.txt",
        content_type="text/plain",
    )
    print("upload_status", status)
    print(text)


if __name__ == "__main__":
    main()

